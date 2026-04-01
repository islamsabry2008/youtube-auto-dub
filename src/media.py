import subprocess
from pathlib import Path
from typing import List
from .models import SubtitleSegment
from .ui import console
from pydub import AudioSegment

def smart_chunk(raw_segments: List[dict]) -> List[SubtitleSegment]:
    if not raw_segments: return []
    chunks, curr_chunk = [], [raw_segments[0]]
    
    for curr in raw_segments[1:]:
        prev = curr_chunk[-1]
        gap = curr['start'] - prev['end']
        duration = curr['end'] - curr_chunk[0]['start']
        
        if gap > 0.8 or duration > 10.0:
            chunks.append(SubtitleSegment(
                start=curr_chunk[0]['start'], end=curr_chunk[-1]['end'],
                source_text=" ".join(s['text'] for s in curr_chunk).strip()
            ))
            curr_chunk = [curr]
        else:
            curr_chunk.append(curr)

    if curr_chunk:
        chunks.append(SubtitleSegment(
            start=curr_chunk[0]['start'], end=curr_chunk[-1]['end'],
            source_text=" ".join(s['text'] for s in curr_chunk).strip()
        ))
    console.step(f"Grouped into {len(chunks)} segments")
    return chunks

def generate_srt(segments: List[SubtitleSegment], output_path: Path):
    def fmt_time(seconds: float) -> str:
        h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            text = seg.translated_text_sub if seg.translated_text_sub else seg.source_text
            f.write(f"{i}\n{fmt_time(seg.start)} --> {fmt_time(seg.end)}\n{text}\n\n")

def mix_dubbing(og_audio: Path, segments: List[SubtitleSegment], output_path: Path):
    console.step("Mixing dubbing with original audio...")
    base_audio = AudioSegment.from_file(og_audio)
    base_audio = base_audio - 12

    for seg in segments:
        if seg.tts_audio_path and seg.tts_audio_path.exists():
            tts_clip = AudioSegment.from_file(seg.tts_audio_path)
            # position in ms
            pos_ms = int(seg.start * 1000)
            base_audio = base_audio.overlay(tts_clip, position=pos_ms)
            
    base_audio.export(output_path, format="wav")

def render_video(video_path: Path, subtitle_path: Path | None, dub_audio_path: Path | None, output_path: Path):
    console.step("Rendering video...")
    cmd = ['ffmpeg', '-y', '-i', str(video_path)]
    
    if dub_audio_path:
        cmd.extend(['-i', str(dub_audio_path)])
        
    vf_filters = []
    if subtitle_path:
        sub_path_str = str(subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:")
        vf_filters.append(f"subtitles='{sub_path_str}'")
        
    if vf_filters:
        cmd.extend(['-vf', ",".join(vf_filters)])
        
    cmd.extend(['-c:v', 'libx264'])
    
    if dub_audio_path:
        cmd.extend(['-c:a', 'aac', '-map', '0:v:0', '-map', '1:a:0'])
    else:
        cmd.extend(['-c:a', 'copy'])
        
    cmd.append(str(output_path))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)