import os
import uuid
import asyncio
import logging
from bot.config import config

logger = logging.getLogger(__name__)

class AudioExtractor:
    """Extract and trim audio from media files using FFmpeg."""

    def __init__(self, download_dir: str = config.DOWNLOAD_DIR):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    async def probe_duration(self, input_path: str) -> float | None:
        """Return media duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
            if process.returncode != 0:
                return None

            duration = float((stdout or b"0").decode().strip() or 0)
            return duration if duration > 0 else None
        except Exception:
            return None

    async def extract_audio(self, input_path: str, duration: int = 20, start_time: int = 0) -> str:
        """
        Extract N seconds of audio starting from start_time.
        Returns path to the trimmed .mp3 file.
        """
        output_path = os.path.join(self.download_dir, f"{uuid.uuid4()}.wav")
        safe_duration = max(6, int(duration))
        safe_start = max(0, int(start_time))

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(safe_start),
            "-i", input_path,
            "-t", str(safe_duration),
            "-vn",
            "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "1",
            output_path
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            timeout = min(90, max(30, safe_duration + 20))
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

            if process.returncode != 0:
                logger.error(f"FFmpeg error: {stderr.decode()[:200]}")
                return None

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            return None

        except asyncio.TimeoutError:
            logger.error("FFmpeg extraction timed out")
            return None
        except Exception as e:
            logger.error(f"Audio extraction error: {e}")
            return None

    def cleanup(self, *paths):
        """Remove temporary files."""
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

audio_extractor = AudioExtractor()
