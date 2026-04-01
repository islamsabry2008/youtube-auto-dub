import subprocess
import yt_dlp
from typing import Optional
from .models import ProjectContext, CACHE_DIR
from .ui import console

def download_project(url: str, browser: Optional[str] = None) -> ProjectContext:
    opts = {
        'format': 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': str(CACHE_DIR / '%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
    }
    if browser: opts['cookiesfrombrowser'] = (browser.lower(),)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info['id']
        video_path = CACHE_DIR / f"{video_id}.mp4"
        audio_path = CACHE_DIR / f"{video_id}.wav"

    if not audio_path.exists() or audio_path.stat().st_size < 1024 * 100:
        console.step("Extracting audio format...")
        subprocess.run(
            ['ffmpeg', '-y', '-i', str(video_path), '-vn', '-acodec', 'pcm_s16le', '-ar', '24000', '-ac', '1', str(audio_path)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    console.step(f"Downloaded source ({video_id})")
    return ProjectContext(video_id=video_id, video_path=video_path, audio_path=audio_path)