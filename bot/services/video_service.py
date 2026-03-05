import os
import uuid
import asyncio
import logging
from bot.config import config

logger = logging.getLogger(__name__)

class VideoService:
    """Specialized service for Telegram Video Note (round video) conversions."""

    def __init__(self, download_dir: str = config.DOWNLOAD_DIR):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    async def to_video_note(self, input_path: str, max_duration: int = 60) -> str:
        """
        Convert any video to a Square MP4 suitable for Telegram Video Note.
        - Crops to square (center)
        - Resizes to 640x640
        - Limits duration to 60s
        - Enforce mp4 container
        """
        output_path = os.path.join(self.download_dir, f"note_{uuid.uuid4()}.mp4")

        # FFmpeg filter: 
        # 1. crop to square based on the smaller dimension
        # 2. scale to 640x640
        # 3. set pixel format to yuv420p (guaranteed compatibility)
        vf_chain = (
            "crop='min(iw,ih)':'min(iw,ih)',"
            "scale=640:640:force_original_aspect_ratio=decrease,"
            "pad=640:640:(ow-iw)/2:(oh-ih)/2,"
            "format=yuv420p"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-t", str(max_duration),
            "-vf", vf_chain,
            "-acodec", "aac",
            "-b:a", "128k",
            "-vcodec", "libx264",
            "-crf", "23",
            "-preset", "veryfast",
            output_path
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

            if process.returncode != 0:
                logger.error(f"FFmpeg video note error: {stderr.decode()[:200]}")
                return None

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            return None

        except asyncio.TimeoutError:
            logger.error("FFmpeg video note conversion timed out")
            return None
        except Exception as e:
            logger.error(f"Video note conversion error: {e}")
            return None

    def cleanup(self, path: str):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

video_service = VideoService()
