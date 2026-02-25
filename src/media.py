"""Media Processing Module for YouTube Auto Dub.

This module handles all audio/video processing operations using FFmpeg.
It provides functionality for:
- Audio duration detection and analysis
- Silence generation for gap filling
- Audio time-stretching and duration fitting (PADDING logic added)
- Video concatenation and rendering (Volume Mixing fixed)
- Audio synchronization and mixing

Author: Nguyen Cong Thuan Huy (mangodxd)
Version: 1.1.0 (Patched)
"""

import subprocess
from pathlib import Path
from typing import List, Dict, Optional

from src.engines import SAMPLE_RATE, AUDIO_CHANNELS


def _get_duration(path: Path) -> float:
    """Get the duration of an audio/video file using FFprobe."""
    if not path.exists():
        print(f"[!] ERROR: Media file not found: {path}")
        return 0.0
    
    try:
        cmd = [
            'ffprobe', '-v', 'error', 
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            str(path)
        ]
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True,
            timeout=60  # Increased from 30s to 60s for better reliability
        )
        
        duration_str = result.stdout.strip()
        if duration_str:
            return float(duration_str)
        else:
            return 0.0
            
    except Exception as e:
        print(f"[!] ERROR: Getting duration failed for {path}: {e}")
        return 0.0


def _generate_silence_segment(duration: float, silence_ref: Path) -> Optional[Path]:
    """Generate a small silence segment for the concat list."""
    if duration <= 0:
        return None
    
    # Use the parent folder of the reference silence file
    output_path = silence_ref.parent / f"gap_{duration:.4f}.wav"
    
    if output_path.exists():
        return output_path

    try:
        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-f', 'lavfi', '-i', f'anullsrc=r={SAMPLE_RATE}:cl=mono',
            '-t', f"{duration:.4f}",
            '-c:a', 'pcm_s16le',
            str(output_path)
        ]
        subprocess.run(cmd, check=True)
        return output_path
    except Exception:
        return None

def _analyze_audio_loudness(audio_path: Path) -> Optional[float]:
    """Analyze audio loudness using FFmpeg volumedetect filter.
    
    Args:
        audio_path: Path to audio file to analyze.
        
    Returns:
        Mean volume in dB, or None if analysis fails.
    """
    if not audio_path.exists():
        return None
        
    try:
        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-i', str(audio_path),
            '-filter:a', 'volumedetect',
            '-f', 'null', '-'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        
        # Parse mean volume from output
        for line in result.stderr.split('\n'):
            if 'mean_volume:' in line:
                # Extract dB value from line like: "mean_volume: -15.2 dB"
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        return float(parts[1])
                    except ValueError:
                        continue
        
        return None
    except Exception:
        return None


def fit_audio(audio_path: Path, target_dur: float) -> Path:
    if not audio_path.exists() or target_dur <= 0:
        return audio_path
    
    actual_dur = _get_duration(audio_path)
    if actual_dur == 0.0:
        return audio_path
    
    out_path = audio_path.parent / f"{audio_path.stem}_fit.wav"
    
    # Increased tolerance from 0.05s to 0.15s for more natural audio
    if actual_dur > target_dur + 0.15:
        ratio = actual_dur / target_dur
        filter_chain = []
        current_ratio = ratio
        
        # Dynamic speed limit: max 1.5x instead of 2.0x to avoid chipmunk effect
        max_speed_ratio = 1.5
        
        while current_ratio > max_speed_ratio:
            filter_chain.append(f"atempo={max_speed_ratio}")
            current_ratio /= max_speed_ratio
            
        if current_ratio > 1.0:
            filter_chain.append(f"atempo={current_ratio:.4f}")
        
        filter_complex = ",".join(filter_chain)
        
        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-i', str(audio_path),
            '-filter:a', f"{filter_complex},aresample=24000",
            '-t', f"{target_dur:.4f}",
            '-c:a', 'pcm_s16le',
            str(out_path)
        ]
    else:
        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-i', str(audio_path),
            '-filter:a', f"apad,aresample=24000",
            '-t', f"{target_dur:.4f}",
            '-c:a', 'pcm_s16le',
            str(out_path)
        ]
    print(f"Fiting {actual_dur:.4f}s to {target_dur:.4f}s")
    
    try:
        subprocess.run(cmd, check=True, timeout=120)
        return out_path
    except Exception:
        return audio_path

def create_concat_file(segments: List[Dict], silence_ref: Path, output_txt: Path) -> None:
    if not segments:
        return
    
    try:
        with open(output_txt, 'w', encoding='utf-8') as f:
            current_timeline = 0.0
            
            for segment in segments:
                start_time = segment['start']
                end_time = segment['end']
                audio_path = segment.get('processed_audio')
                
                gap = start_time - current_timeline
                if gap > 0.01:
                    silence_gap = _generate_silence_segment(gap, silence_ref)
                    if silence_gap:
                        f.write(f"file '{silence_gap.resolve().as_posix()}'\n")
                        current_timeline += gap
                
                if audio_path and audio_path.exists():
                    f.write(f"file '{audio_path.resolve().as_posix()}'\n")
                    current_timeline += (end_time - start_time)
                else:
                    dur = end_time - start_time
                    silence_err = _generate_silence_segment(dur, silence_ref)
                    if silence_err:
                        f.write(f"file '{silence_err.resolve().as_posix()}'\n")
                    current_timeline += dur
                    
    except Exception as e:
        raise RuntimeError(f"Failed to create concat manifest: {e}")


def render_video(video_path: Path, concat_file: Path, output_path: Path, subtitle_path: Optional[Path] = None) -> None:
    """Render final video with Dynamic Volume Mixing."""
    if not video_path.exists() or not concat_file.exists():
        raise FileNotFoundError("Input files for rendering missing")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"[*] Rendering final video...")
        
        # DYNAMIC VOLUME MIXING STRATEGY:
        # Analyze original audio loudness to determine optimal background volume
        original_loudness = _analyze_audio_loudness(video_path)
        
        if original_loudness is not None:
            # Calculate background volume based on loudness analysis
            # Target: voice should be 10-15dB louder than background
            if original_loudness > -10:  # Very loud audio
                bg_volume = 0.08  # 8% - reduce more for loud content
            elif original_loudness > -20:  # Normal audio
                bg_volume = 0.15  # 15% - standard reduction
            else:  # Quiet audio
                bg_volume = 0.25  # 25% - reduce less for quiet content
                
            print(f"[*] Dynamic volume mixing: original={original_loudness:.1f}dB, bg_volume={bg_volume*100:.0f}%")
        else:
            # Fallback to default if analysis fails
            bg_volume = 0.15
            print(f"[*] Using default volume mixing: bg_volume={bg_volume*100:.0f}%")
        
        filter_complex = (
            f"[0:a]volume={bg_volume}[bg]; "
            "[bg][1:a]amix=inputs=2:duration=first:dropout_transition=0[outa]"
        )

        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-i', str(video_path),
            '-f', 'concat', '-safe', '0', '-i', str(concat_file),
            '-filter_complex', filter_complex,
            '-map', '0:v', 
            '-map', '[outa]',
            '-c:v', 'copy',      # Fast video copy (if no subs)
            '-c:a', 'aac', '-b:a', '192k',
            '-ar', str(SAMPLE_RATE),
            '-ac', str(AUDIO_CHANNELS),
            '-shortest'
        ]
        
        # Handle Hard Subtitles (Requires re-encoding)
        if subtitle_path:
            # Escape path for FFmpeg filter
            sub_path = str(subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:")
            
            # Switch video codec to libx264 for re-encoding
            idx_copy = cmd.index('copy')
            cmd[idx_copy] = 'libx264'
            
            # Insert subtitle filter
            cmd.insert(idx_copy, '-vf')
            cmd.insert(idx_copy + 1, f"subtitles='{sub_path}'")
        
        cmd.append(str(output_path))
        
        # Run rendering
        subprocess.run(cmd, check=True, timeout=None) # No timeout for rendering
        
        if not output_path.exists():
            raise RuntimeError("Output file not created")
            
        print(f"[+] Video rendered successfully: {output_path}")
        
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg rendering failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Rendering error: {e}")


def generate_srt(segments: List[Dict], output_path: Path) -> None:
    """Generate SRT subtitle file."""
    if not segments: return
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                start = _format_timestamp_srt(segment['start'])
                end = _format_timestamp_srt(segment['end'])
                text = segment.get('trans_text', '').strip()
                
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
                
        print(f"[+] SRT subtitles generated")
    except Exception as e:
        print(f"[!] Warning: SRT generation failed: {e}")


def _format_timestamp_srt(seconds: float) -> str:
    """Convert seconds to HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"