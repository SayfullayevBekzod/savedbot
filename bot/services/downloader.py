import yt_dlp
import os
import asyncio
import logging
import uuid
import time
from typing import Optional, Dict, Any
from bot.config import config

logger = logging.getLogger(__name__)

class DownloaderService:
    def __init__(self, download_dir: str = config.DOWNLOAD_DIR):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        self.cookie_path = "cookies.txt"

    async def get_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch video info including available formats."""
        from bot.services.antiban import antiban_service
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 3,  # Ultra-fast timeout
            'extractor_retries': 0,  # No retries for speed
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'no_playlist': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'referer': 'https://www.instagram.com/',
            'geo_bypass': True,
            'source_address': '0.0.0.0',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],  # Fastest client only
                    'player_skip': ['webpage', 'configs', 'js']
                }
            }
        }
        
        proxy = antiban_service.get_random_proxy()
        if proxy: ydl_opts['proxy'] = proxy
        
        cookie_file = antiban_service.get_random_cookie_file()
        if cookie_file: ydl_opts['cookiefile'] = cookie_file

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: self._get_info(url, ydl_opts))
            
            if not info:
                return None

            # Filter formats: we want mp4 with audio OR best merged
            formats = []
            seen_heights = set()
            
            # Sort by quality
            raw_formats = sorted(
                info.get('formats', []), 
                key=lambda f: (f.get('height') or 0, f.get('tbr') or 0), 
                reverse=True
            )

            for f in raw_formats:
                height = f.get('height')
                ext = f.get('ext')
                
                # Only take standard heights, unique ones, and mp4/webm
                if height and height >= 360 and height not in seen_heights and ext in ['mp4', 'webm', 'm4a']:
                    formats.append({
                        'format_id': f.get('format_id'),
                        'height': height,
                        'ext': ext,
                        'filesize': f.get('filesize') or f.get('filesize_approx')
                    })
                    seen_heights.add(height)
                
                if len(formats) >= 5: break

            return {
                'id': info.get('id'),
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'formats': formats,
                'platform': self._detect_platform(url)
            }
        except Exception as e:
            logger.error(f"Downloader.get_info error [{url}]: {e}")
            return None

    def _get_info(self, url: str, opts: dict):
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def download(self, url: str, format_id: str = None, max_size_mb: int = 50) -> Optional[Dict[str, Any]]:
        """Download video/audio with unique UUID filename and return metadata."""
        from bot.services.antiban import antiban_service
        
        file_uuid = str(uuid.uuid4())
        is_audio_request = format_id == "audio"

        if is_audio_request:
            fmt = "bestaudio/best"
        elif format_id:
            fmt = f"{format_id}+bestaudio/{format_id}"
        else:
            fmt = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
        
        ydl_opts = {
            'format': fmt,
            'outtmpl': os.path.join(self.download_dir, f'{file_uuid}.%(ext)s'),
            'noprogress': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'no_playlist': True,
            # Maximum speed optimizations
            'concurrent_fragment_downloads': 256,  # Max parallel fragments
            'socket_timeout': 5,  # Fast timeout
            'retries': 1,  # Minimal retries
            'fragment_retries': 1,
            'extractor_retries': 0,  # No retries
            'buffersize': 16 * 1024 * 1024, # 16MB buffer
            'http_chunk_size': 64 * 1024 * 1024, # 64MB chunks
            'fragment_buffer_size': 32 * 1024 * 1024, # 32MB fragment buffer
            'hls_prefer_native': True,
            'hls_use_mpegts': True,
            'geo_bypass': True,
            'source_address': '0.0.0.0',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'referer': 'https://www.instagram.com/',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web_creator']
                }
            },
            'http_headers': {
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
        if is_audio_request:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            ydl_opts['merge_output_format'] = 'mp4'

        # Size matching filter
        def size_filter(info_dict, *, incomplete):
            filesize = info_dict.get('filesize') or info_dict.get('filesize_approx')
            if filesize and filesize > max_size_mb * 1024 * 1024:
                return f'File is too large ({filesize / 1024 / 1024:.1f}MB > {max_size_mb}MB limit)'
            return None
            
        ydl_opts['match_filter'] = size_filter

        # Anti-ban rotation
        if format_id:
            if os.path.exists(self.cookie_path):
                ydl_opts['cookiefile'] = self.cookie_path
            else:
                cookie_file = antiban_service.get_random_cookie_file()
                if cookie_file:
                    ydl_opts['cookiefile'] = cookie_file
        else:
            proxy = antiban_service.get_random_proxy()
            if proxy: ydl_opts['proxy'] = proxy
            cookie_file = antiban_service.get_random_cookie_file()
            if cookie_file: ydl_opts['cookiefile'] = cookie_file

        try:
            loop = asyncio.get_event_loop()
            download_info = await loop.run_in_executor(None, lambda: self._perform_download(url, ydl_opts))
            
            if download_info:
                preferred_ext = "mp3" if is_audio_request else "mp4"
                filename = os.path.join(self.download_dir, f"{file_uuid}.{preferred_ext}")
                if not os.path.exists(filename):
                    for f in os.listdir(self.download_dir):
                        if f.startswith(file_uuid):
                            filename = os.path.join(self.download_dir, f)
                            break
                
                if not os.path.exists(filename):
                     return {"error": "File not found locally."}

                actual_size = os.path.getsize(filename)
                return {
                    'file_path': filename,
                    'title': download_info.get('title', 'Video'),
                    'filesize': actual_size,
                    'platform': self._detect_platform(url),
                    'width': download_info.get('width'),
                    'height': download_info.get('height'),
                    'id': download_info.get('id'),
                    'uploader': download_info.get('uploader'),
                    'is_audio': is_audio_request
                }
            return {"error": "Download failed."}
        except Exception as e:
            logger.error(f"Downloader error [{url}]: {e}")
            return {"error": str(e)}

    def _perform_download(self, url: str, opts: dict):
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    async def fast_download(self, url: str, max_size_mb: int = 50) -> Optional[Dict[str, Any]]:
        """Single-pass download: extract info + download in one yt-dlp call."""
        from bot.services.antiban import antiban_service

        file_uuid = str(uuid.uuid4())
        max_height = config.AUTO_VIDEO_MAX_HEIGHT

        fmt = (
            f'bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/'
            f'bestvideo[height<={max_height}]+bestaudio/'
            f'best[height<={max_height}][ext=mp4]/'
            f'best[ext=mp4]/best'
        )

        ydl_opts = {
            'format': fmt,
            'outtmpl': os.path.join(self.download_dir, f'{file_uuid}.%(ext)s'),
            'merge_output_format': 'mp4',
            'noprogress': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'no_playlist': True,
            # Speed optimizations
            'concurrent_fragment_downloads': config.DOWNLOAD_CONCURRENT_FRAGMENTS,
            'socket_timeout': 15,
            'retries': 5,
            'fragment_retries': 5,
            'extractor_retries': 2,
            'buffersize': 4 * 1024 * 1024,
            'http_chunk_size': 20 * 1024 * 1024,
            'hls_prefer_native': True,
            'hls_use_mpegts': True,
            'geo_bypass': True,
            'source_address': '0.0.0.0',
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
            'referer': 'https://www.instagram.com/',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web_creator']
                }
            },
            'http_headers': {
                'Accept-Language': 'en-US,en;q=0.9',
            },
        }

        def size_filter(info_dict, *, incomplete):
            filesize = info_dict.get('filesize') or info_dict.get('filesize_approx')
            if filesize and filesize > max_size_mb * 1024 * 1024:
                return f'File too large ({filesize / 1024 / 1024:.1f}MB > {max_size_mb}MB)'
            return None

        ydl_opts['match_filter'] = size_filter

        proxy = antiban_service.get_random_proxy()
        if proxy: ydl_opts['proxy'] = proxy
        cookie_file = antiban_service.get_random_cookie_file()
        if cookie_file: ydl_opts['cookiefile'] = cookie_file

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: self._perform_download(url, ydl_opts))

            if not info:
                return {"error": "Download failed."}

            filename = os.path.join(self.download_dir, f"{file_uuid}.mp4")
            if not os.path.exists(filename):
                for f in os.listdir(self.download_dir):
                    if f.startswith(file_uuid):
                        filename = os.path.join(self.download_dir, f)
                        break

            if not os.path.exists(filename):
                return {"error": "File not found locally."}

            actual_size = os.path.getsize(filename)
            return {
                'file_path': filename,
                'title': info.get('title', 'Video'),
                'filesize': actual_size,
                'platform': self._detect_platform(url),
                'width': info.get('width'),
                'height': info.get('height'),
                'id': info.get('id'),
                'uploader': info.get('uploader'),
                'is_audio': False,
            }
        except Exception as e:
            logger.error(f"Fast download error [{url}]: {e}")
            return {"error": str(e)}

    def _detect_platform(self, url: str) -> str:
        url_lower = url.lower()
        if "instagram.com" in url_lower: return "Instagram"
        if "youtube.com" in url_lower or "youtu.be" in url_lower: return "YouTube"
        if "tiktok.com" in url_lower: return "TikTok"
        if "facebook.com" in url_lower or "fb.watch" in url_lower: return "Facebook"
        return "Generic"

    async def cleanup_old_files(self, directory: str = None):
        """Cleanup temporary files older than 24h."""
        target = directory or self.download_dir
        now = time.time()
        for f in os.listdir(target):
            fpath = os.path.join(target, f)
            if os.stat(fpath).st_mtime < now - 86400:
                try: os.remove(fpath)
                except: pass

downloader = DownloaderService()
