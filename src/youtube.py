"""YouTube Content Download Module for YouTube Auto Dub.

This module provides a robust interface for downloading YouTube content
using yt-dlp. It handles:
- Video and audio extraction from YouTube URLs
- Authentication via cookies or browser integration
- Format selection and quality optimization
- Error handling and retry logic
- Metadata extraction and validation

Author: Nguyen Cong Thuan Huy (mangodxd)
Version: 1.0.0
"""

import yt_dlp
from pathlib import Path
from typing import Optional, Dict, Any
from src.engines import CACHE_DIR


def _getOpts(browser: Optional[str] = None, 
             cookies_file: Optional[str] = None, 
             quiet: bool = True) -> Dict[str, Any]:
    """Generate common yt-dlp options with authentication configuration.
    
    Args:
        browser: Browser name for cookie extraction (chrome, edge, firefox).
                If provided, cookies will be extracted from this browser.
        cookies_file: Path to cookies.txt file in Netscape format.
                     Takes priority over browser extraction if both provided.
        quiet: Whether to suppress yt-dlp output messages.
        
    Returns:
        Dictionary of yt-dlp options.
        
    Raises:
        ValueError: If invalid browser name is provided.
        
    Note:
        Priority order: cookies_file > browser > no authentication.
    """
    opts = {
        'quiet': quiet,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    if cookies_file:
        cookies_path = Path(cookies_file)
        if not cookies_path.exists():
            raise FileNotFoundError(f"Cookies file not found: {cookies_file}")
        
        opts['cookiefile'] = str(cookies_path)
        print(f"[*] Using cookies file: {cookies_file}")
        
    elif browser:
        valid_browsers = ['chrome', 'firefox', 'edge', 'safari', 'opera', 'brave']
        browser_lower = browser.lower()
        
        if browser_lower not in valid_browsers:
            raise ValueError(f"Invalid browser '{browser}'. Supported: {', '.join(valid_browsers)}")
        
        opts['cookiesfrombrowser'] = (browser_lower,)
        print(f"[*] Extracting cookies from browser: {browser}")
        
    else:
        print(f"[*] No authentication configured (public videos only)")
    
    return opts


def getId(url: str, 
          browser: Optional[str] = None, 
          cookies_file: Optional[str] = None) -> str:
    """Extract YouTube video ID from URL with authentication support.
    
    Args:
        url: YouTube video URL to extract ID from.
        browser: Browser name for cookie extraction.
        cookies_file: Path to cookies.txt file.
        
    Returns:
        YouTube video ID as string.
        
    Raises:
        ValueError: If URL is invalid or video ID cannot be extracted.
        RuntimeError: If yt-dlp fails to extract information.
        
    Note:
        This function validates the URL and extracts metadata
        without downloading the actual content.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")
    
    if not any(domain in url.lower() for domain in ['youtube.com', 'youtu.be']):
        raise ValueError(f"Invalid YouTube URL: {url}")
    
    try:
        print(f"[*] Extracting video ID from: {url[:50]}...")
        
        opts = _getOpts(browser=browser, cookies_file=cookies_file)
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                video_id = info.get('id')
                
                if not video_id:
                    raise RuntimeError("No video ID found in extracted information")
                
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
                uploader = info.get('uploader', 'Unknown')
                
                print(f"[+] Video ID extracted: {video_id}")
                print(f"    Title: {title[:50]}{'...' if len(title) > 50 else ''}")
                print(f"    Duration: {duration}s ({duration//60}:{duration%60:02d})")
                print(f"    Uploader: {uploader}")
                
                return video_id
                
            except yt_dlp.DownloadError as e:
                if "Sign in to confirm" in str(e) or "private video" in str(e).lower():
                    raise ValueError(f"Authentication required for this video. Please use --browser or --cookies. Original error: {e}")
                else:
                    raise RuntimeError(f"yt-dlp extraction failed: {e}")
                    
    except Exception as e:
        if isinstance(e, (ValueError, RuntimeError)):
            raise
        raise RuntimeError(f"Failed to extract video ID: {e}") from e


def downloadVideo(url: str, 
                  browser: Optional[str] = None, 
                  cookies_file: Optional[str] = None) -> Path:
    """Download the best quality video with audio from YouTube.
    
    Args:
        url: YouTube video URL to download.
        browser: Browser name for cookie extraction.
        cookies_file: Path to cookies.txt file.
        
    Returns:
        Path to the downloaded video file.
        
    Raises:
        ValueError: If URL is invalid or authentication is required.
        RuntimeError: If download fails or file is corrupted.
        
    Note:
        This function downloads both video and audio in a single file.
        If the video already exists in cache, it returns the existing file.
    """
    try:
        video_id = getId(url, browser=browser, cookies_file=cookies_file)
    except Exception as e:
        raise ValueError(f"Failed to validate video URL: {e}") from e
    
    out_path = CACHE_DIR / f"{video_id}.mp4"
    
    if out_path.exists():
        file_size = out_path.stat().st_size
        if file_size > 1024 * 1024:
            print(f"[*] Video already cached: {out_path}")
            return out_path
        else:
            print(f"[!] WARNING: Cached video seems too small ({file_size} bytes), re-downloading")
            out_path.unlink()
    
    try:
        print(f"[*] Downloading video: {video_id}")
        
        opts = _getOpts(browser=browser, cookies_file=cookies_file)
        opts.update({
            'format': (
                'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/'
                'best[ext=mp4]/'
                'best'
            ),
            'outtmpl': str(out_path),
            'merge_output_format': 'mp4',
            'postprocessors': [],
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        
        if not out_path.exists():
            raise RuntimeError(f"Video file not created after download: {out_path}")
        
        file_size = out_path.stat().st_size
        if file_size < 1024 * 1024:
            raise RuntimeError(f"Downloaded video file is too small: {file_size} bytes")
        
        print(f"[+] Video downloaded successfully:")
        print(f"    File: {out_path}")
        print(f"    Size: {file_size / (1024*1024):.1f} MB")
        
        return out_path
        
    except yt_dlp.DownloadError as e:
        error_msg = str(e).lower()
        if "sign in to confirm" in error_msg or "private video" in error_msg:
            raise ValueError(
                f"Authentication required for this video. Please try:\n"
                f"1. Close all browser windows and use --browser\n"
                f"2. Export fresh cookies.txt and use --cookies\n"
                f"3. Check if video is public/accessible\n"
                f"Original error: {e}"
            )
        else:
            raise RuntimeError(f"Video download failed: {e}")
            
    except Exception as e:
        if out_path.exists():
            out_path.unlink()
        raise RuntimeError(f"Video download failed: {e}") from e


def downloadAudio(url: str, 
                  browser: Optional[str] = None, 
                  cookies_file: Optional[str] = None) -> Path:
    """Download audio-only from YouTube for transcription processing.
    
    Args:
        url: YouTube video URL to extract audio from.
        browser: Browser name for cookie extraction.
        cookies_file: Path to cookies.txt file.
        
    Returns:
        Path to the downloaded WAV audio file.
        
    Raises:
        ValueError: If URL is invalid or authentication is required.
        RuntimeError: If audio download or conversion fails.
        
    Note:
        The output is always in WAV format at the project's sample rate
        for consistency with the transcription pipeline.
    """
    try:
        video_id = getId(url, browser=browser, cookies_file=cookies_file)
    except Exception as e:
        raise ValueError(f"Failed to validate video URL: {e}") from e
    
    temp_path = CACHE_DIR / f"{video_id}"
    final_path = CACHE_DIR / f"{video_id}.wav"
    
    if final_path.exists():
        file_size = final_path.stat().st_size
        if file_size > 1024 * 100:
            print(f"[*] Audio already cached: {final_path}")
            return final_path
        else:
            print(f"[!] WARNING: Cached audio seems too small ({file_size} bytes), re-downloading")
            final_path.unlink()
    
    try:
        print(f"[*] Downloading audio: {video_id}")
        
        opts = _getOpts(browser=browser, cookies_file=cookies_file)
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': str(temp_path),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        
        if not final_path.exists():
            temp_files = list(CACHE_DIR.glob(f"{video_id}.*"))
            if temp_files:
                print(f"[!] WARNING: Expected {final_path} but found {temp_files[0]}")
                final_path = temp_files[0]
            else:
                raise RuntimeError(f"Audio file not created after download: {final_path}")
        
        file_size = final_path.stat().st_size
        if file_size < 1024 * 100:
            raise RuntimeError(f"Downloaded audio file is too small: {file_size} bytes")
        
        print(f"[+] Audio downloaded successfully:")
        print(f"    File: {final_path}")
        print(f"    Size: {file_size / (1024*1024):.1f} MB")
        
        try:
            from src.media import _get_duration
            duration = _get_duration(final_path)
            if duration > 0:
                print(f"    Duration: {duration:.1f}s ({duration//60}:{duration%60:02d})")
            else:
                print(f"[!] WARNING: Could not determine audio duration")
        except Exception as e:
            print(f"[!] WARNING: Audio validation failed: {e}")
        
        return final_path
        
    except yt_dlp.DownloadError as e:
        error_msg = str(e).lower()
        if "sign in to confirm" in error_msg or "private video" in error_msg:
            raise ValueError(
                f"Authentication required for this video. Please try:\n"
                f"1. Close all browser windows and use --browser\n"
                f"2. Export fresh cookies.txt and use --cookies\n"
                f"3. Check if video is public/accessible\n"
                f"Original error: {e}"
            )
        else:
            raise RuntimeError(f"Audio download failed: {e}")
            
    except Exception as e:
        for path in [temp_path, final_path]:
            if path.exists():
                path.unlink()
        raise RuntimeError(f"Audio download failed: {e}") from e
