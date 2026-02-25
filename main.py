#!/usr/bin/env python3
"""YouTube Auto Sub - Automated Video Subtitling Pipeline.

This module provides a command-line interface for automatically generating subtitles
for YouTube videos using AI/ML technologies.

Example:
    python main.py "https://youtube.com/watch?v=VIDEO_ID" --lang es

Author: Nguyen Cong Thuan Huy (mangodxd)
Version: 1.0.0
License: MIT
"""

import argparse
import shutil
import subprocess
import time
import random
from pathlib import Path
from typing import Optional
import asyncio
import torch

import src.engines
import src.youtube
import src.media


def _checkDeps() -> None:
    """Verifies critical dependencies are installed and accessible.
    
    Args:
        None
        
    Returns:
        None
        
    Raises:
        SystemExit: If any critical dependency is missing.
        
    Note:
        Checks for FFmpeg, FFprobe binaries and PyTorch installation.
    """
    from shutil import which
    
    missing = []
    if not which("ffmpeg"):
        missing.append("ffmpeg")
    if not which("ffprobe"):
        missing.append("ffprobe")
    
    if missing:
        print(f"[!] CRITICAL: Missing dependencies: {', '.join(missing)}")
        print("    Please install FFmpeg and add it to your System PATH.")
        print("    Download: https://ffmpeg.org/download.html")
        exit(1)

    try:
        import torch
        print(f"[*] PyTorch {torch.__version__} | CUDA Available: {torch.cuda.is_available()}")
    except ImportError:
        print("[!] CRITICAL: PyTorch not installed.")
        print("    Install with: pip install torch")
        exit(1)


def _cleanup() -> None:
    """Clean up temporary directory with retry mechanism for Windows file locks.
    
    Args:
        None
        
    Returns:
        None
        
    Note:
        Windows can lock files temporarily, especially after FFmpeg operations.
        Implements exponential backoff retry strategy.
        If cleanup fails after max retries, pipeline will continue.
    """
    max_retries = 5
    
    for attempt in range(max_retries):
        try:
            if src.engines.TEMP_DIR.exists():
                shutil.rmtree(src.engines.TEMP_DIR)
            src.engines.TEMP_DIR.mkdir(parents=True, exist_ok=True)
            return
        except PermissionError:
            wait_time = 0.5 * (2 ** attempt)
            print(f"[-] File locked (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time}s...")
            time.sleep(wait_time)
            
    print(f"[!] WARNING: Could not fully clean temp directory after {max_retries} attempts.")
    print(f"    Files may persist in: {src.engines.TEMP_DIR}")


def main() -> None:
    """Main entry point for the YouTube Auto Sub pipeline.
    
    Args:
        None
        
    Returns:
        None
        
    Raises:
        SystemExit: On critical errors or user interruption.
        
    Note:
        Orchestrates the complete subtitling process:
        1. Dependency validation and environment setup
        2. Video/audio download from YouTube
        3. Speech transcription using Whisper
        4. Smart audio chunking for optimal processing
        5. Translation to target language
        6. Subtitle file generation
        7. Final video rendering with subtitles
    """
    parser = argparse.ArgumentParser(
        description="YouTube Auto Sub - Automated Video Subtitling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python main.py "https://youtube.com/watch?v=VIDEO_ID" --lang es
  python main.py "https://youtube.com/watch?v=VIDEO_ID" --lang fr --gpu
  python main.py "https://youtube.com/watch?v=VIDEO_ID" --lang ja --browser chrome
  python main.py "https://youtube.com/watch?v=VIDEO_ID" --whisper_model large-v3
        """
    )
    
    parser.add_argument("url", help="YouTube video URL to subtitle")
    parser.add_argument(
        "--lang", "-l", 
        default="es",
        help="Target language ISO code (e.g., es, fr, ja, vi)."
    )
    parser.add_argument(
        "--browser", "-b", 
        help="Browser to extract cookies from (chrome, edge, firefox). Close browser first!"
    )
    parser.add_argument(
        "--cookies", "-c", 
        help="Path to cookies.txt file (Netscape format) for YouTube authentication"
    )
    parser.add_argument(
        "--gpu", 
        action="store_true", 
        help="Use GPU acceleration for Whisper (requires CUDA)"
    )
    parser.add_argument(
        "--whisper_model", "-wm",
        help="Whisper model to use (tiny, base, small, medium, large-v3). Default: auto-select based on VRAM"
    )
    
    args = parser.parse_args()

    print("\n" + "="*60)
    print("YOUTUBE AUTO SUB - INITIALIZING")
    print("="*60)
    
    _checkDeps()
    _cleanup()
    
    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"
    print(f"[*] Using device: {device.upper()}")
    
    # Set Whisper model based on user input or auto-selection
    if args.whisper_model:
        src.engines.ASR_MODEL = args.whisper_model
        print(f"[*] Using specified Whisper model: {args.whisper_model}")
    else:
        print(f"[*] Auto-selected Whisper model: {src.engines.ASR_MODEL} (based on VRAM)")
    
    engine = src.engines.Engine(device)
    
    print(f"\n{'='*60}")
    print(f"STEP 1: DOWNLOADING CONTENT")
    print(f"{'='*60}")
    print(f"[*] Target URL: {args.url}")
    print(f"[*] Target Language: {args.lang.upper()}")
    
    try:
        videoPath = src.youtube.downloadVideo(
            args.url, 
            browser=args.browser, 
            cookies_file=args.cookies
        )
        audioPath = src.youtube.downloadAudio(
            args.url, 
            browser=args.browser, 
            cookies_file=args.cookies
        )
        print(f"[+] Video downloaded: {videoPath}")
        print(f"[+] Audio extracted: {audioPath}")
    except Exception as e:
        print(f"\n[!] DOWNLOAD FAILED: {e}")
        print("\n[-] TROUBLESHOOTING TIPS:")
        print("    1. Close all browser windows if using --browser")
        print("    2. Export fresh cookies.txt and use --cookies")
        print("    3. Check if video is private/region-restricted")
        print("    4. Verify YouTube URL is correct")
        return

    print(f"\n{'='*60}")
    print(f"STEP 2: SPEECH TRANSCRIPTION")
    print(f"{'='*60}")
    print(f"[*] Transcribing audio with Whisper ({src.engines.ASR_MODEL})...")
    
    raw_segments = engine.transcribeSafe(audioPath)
    print(f"[+] Transcription complete: {len(raw_segments)} segments")
    
    if len(raw_segments) > 0:
        print(f"[*] Sample segment: '{raw_segments[0]['text'][:50]}...'")
    
    print(f"\n{'='*60}")
    print(f"STEP 3: INTELLIGENT CHUNKING")
    print(f"{'='*60}")
    
    chunks = src.engines.smartChunk(raw_segments)
    print(f"[+] Optimized {len(raw_segments)} raw segments into {len(chunks)} chunks")
    print(f"[*] Average chunk duration: {sum(c['end']-c['start'] for c in chunks)/len(chunks):.2f}s")

    print(f"\n{'='*60}")
    print(f"STEP 4: TRANSLATION ({args.lang.upper()})")
    print(f"{'='*60}")
    
    texts = [c['text'] for c in chunks]
    print(f"[*] Translating {len(texts)} text segments...")
    
    translated_texts = engine.translateSafe(texts, args.lang)
    
    for i, chunk in enumerate(chunks):
        chunk['trans_text'] = translated_texts[i]
    
    print(f"[+] Translation complete")
    
    if len(chunks) > 0:
        original = chunks[0]['text'][:50]
        translated = chunks[0]['trans_text'][:50]
        print(f"[*] Sample: '{original}' -> '{translated}'")

    print(f"\n{'='*60}")
    print(f"STEP 5: SUBTITLE GENERATION")
    print(f"{'='*60}")
    
    subtitle_path = src.engines.TEMP_DIR / "subtitles.srt"
    src.media.generate_srt(chunks, subtitle_path)
    print(f"[+] Subtitles generated: {subtitle_path}")

    print(f"\n{'='*60}")
    print(f"STEP 6: FINAL VIDEO RENDERING")
    print(f"{'='*60}")
    
    try:
        video_name = videoPath.stem
        out_name = f"subtitled_{args.lang}_{video_name}.mp4"
        final_output = src.engines.OUTPUT_DIR / out_name
        
        print(f"[*] Rendering final video with subtitles...")
        print(f"    Source: {videoPath}")
        print(f"    Output: {final_output}")
        print(f"    Subtitles: {subtitle_path}")
        
        src.media.render_video(videoPath, None, final_output, subtitle_path=subtitle_path)
        
        if final_output.exists():
            file_size = final_output.stat().st_size / (1024 * 1024)
            print(f"\n[+] SUCCESS! Video rendered successfully.")
            print(f"    Output: {final_output}")
        else:
            print(f"\n[!] ERROR: Output file not created at {final_output}")
            
    except Exception as e:
        print(f"\n[!] RENDERING FAILED: {e}")
        print("[-] This may be due to:")
        print("    1. Corrupted audio chunks")
        print("    2. FFmpeg compatibility issues")
        print("    3. Insufficient disk space")
        return
        
    finally:
        print(f"\n{'='*60}")
        print("YOUTUBE AUTO SUB - PIPELINE COMPLETE")
        print(f"{'='*60}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Process interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n[!] UNEXPECTED ERROR: {e}")
        print("[-] Please report this issue with the full error message")
        exit(1)