"""Core utilities and exceptions for YouTube Auto Sub.

This module consolidates shared utilities, exceptions, and helper functions
used across the entire pipeline to reduce code duplication.

Author: Nguyen Cong Thuan Huy (mangodxd)
Version: 1.0.0
"""

import subprocess
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Union


class YouTubeAutoSubError(Exception):
    """Base exception for all YouTube Auto Sub errors."""
    pass


class ModelLoadError(YouTubeAutoSubError):
    """Raised when AI/ML model fails to load."""
    pass


class AudioProcessingError(YouTubeAutoSubError):
    """Raised when audio processing operations fail."""
    pass


class TranscriptionError(YouTubeAutoSubError):
    """Raised when speech transcription fails."""
    pass


class TranslationError(YouTubeAutoSubError):
    """Raised when text translation fails."""
    pass


class TTSError(YouTubeAutoSubError):
    """Raised when text-to-speech synthesis fails."""
    pass


class VideoProcessingError(YouTubeAutoSubError):
    """Raised when video processing operations fail."""
    pass


class ConfigurationError(YouTubeAutoSubError):
    """Raised when configuration is invalid or missing."""
    pass


class DependencyError(YouTubeAutoSubError):
    """Raised when required dependencies are missing."""
    pass


class ValidationError(YouTubeAutoSubError):
    """Raised when input validation fails."""
    pass


class ResourceError(YouTubeAutoSubError):
    """Raised when system resources are insufficient."""
    pass


def _handleError(error: Exception, context: str = "") -> None:
    """Centralized error handling with context.
    
    Args:
        error: The exception that occurred.
        context: Additional context about where the error occurred.
        
    Returns:
        None
    """
    if context:
        print(f"[!] ERROR in {context}: {error}")
    else:
        print(f"[!] ERROR: {error}")
    
    print(f"    Full traceback: {traceback.format_exc()}")




def _runFFmpegCmd(cmd: List[str], timeout: int = 300, description: str = "FFmpeg operation") -> None:
    """Run FFmpeg command with consistent error handling.
    
    Args:
        cmd: FFmpeg command to run.
        timeout: Command timeout in seconds.
        description: Description for error messages.
        
    Raises:
        RuntimeError: If FFmpeg command fails.
    """
    try:
        subprocess.run(cmd, check=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{description} timed out")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"{description} failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error during {description}: {e}")


def _validateAudioFile(file_path: Path, min_size: int = 1024) -> bool:
    """Validate that audio file exists and has minimum size.
    
    Args:
        file_path: Path to audio file.
        min_size: Minimum file size in bytes.
        
    Returns:
        True if file is valid, False otherwise.
    """
    if not file_path.exists():
        return False
    
    if file_path.stat().st_size < min_size:
        return False
    
    return True


def _safeFileDelete(file_path: Path) -> None:
    """Safely delete file with error handling.
    
    Args:
        file_path: Path to file to delete.
        
    Returns:
        None
    """
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        print(f"[!] WARNING: Could not delete file {file_path}: {e}")



class ProgressTracker:
    """Simple progress tracking for long operations."""
    
    def __init__(self, total: int, description: str = "Processing", update_interval: int = 10):
        """Initialize progress tracker.
        
        Args:
            total: Total number of items to process.
            description: Description for progress messages.
            update_interval: How often to update progress (every N items).
        """
        self.total = total
        self.description = description
        self.update_interval = update_interval
        self.current = 0
    
    def update(self, increment: int = 1) -> None:
        """Update progress counter.
        
        Args:
            increment: Number of items processed.
            
        Returns:
            None
        """
        self.current += increment
        
        if self.current % self.update_interval == 0 or self.current >= self.total:
            progress = (self.current / self.total) * 100
            print(f"[-] {self.description}: {self.current}/{self.total} ({progress:.1f}%)", end='\r')
            
            if self.current >= self.total:
                print()
