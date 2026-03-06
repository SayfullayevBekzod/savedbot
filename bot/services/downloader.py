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

    async def get_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch video info including available formats with automatic cookie retry."""
        from bot.services.antiban import antiban_service
        
        ydl_base_opts = {
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
        
        # Try with different cookies on failure
        max_retries = 2
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                ydl_opts = dict(ydl_base_opts)
                
                proxy = antiban_service.get_random_proxy()
                if proxy: ydl_opts['proxy'] = proxy
                
                cookie_file = antiban_service.get_random_cookie_file()
                if cookie_file: ydl_opts['cookiefile'] = cookie_file
                
                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(None, lambda: self._get_info(url, ydl_opts, cookie_file))
                
                if not info:
                    retries += 1
                    continue

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
                last_error = str(e)
                retries += 1
                logger.warning(f"get_info attempt {retries} failed [{url}]: {last_error}")
        
        logger.error(f"Downloader.get_info error [{url}]: {last_error}")
        return None

    def _get_info(self, url: str, opts: dict, cookie_file: str = None):
        """Get info with error tracking for cookies"""
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info and cookie_file:
                    from bot.services.antiban import antiban_service
                    antiban_service.mark_cookie_working(cookie_file)
                return info
        except Exception as e:
            if cookie_file:
                from bot.services.antiban import antiban_service
                antiban_service.mark_cookie_failed(cookie_file, str(e))
            raise

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

        # Use new retry logic with automatic cookie rotation
        return await self._download_with_cookie_retry(
            url=url,
            format_id=format_id,
            max_size_mb=max_size_mb,
            is_audio=is_audio_request,
            file_uuid=file_uuid,
            ydl_base_opts=ydl_opts,
            max_retries=3
        )

    def _perform_download(self, url: str, opts: dict, cookie_file: str = None):
        """Perform download with error tracking for cookies"""
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(url, download=True)
                if cookie_file and result:
                    # Mark cookie as working if download succeeded
                    from bot.services.antiban import antiban_service
                    antiban_service.mark_cookie_working(cookie_file)
                return result
        except Exception as e:
            # Mark cookie as failed if it was used
            if cookie_file:
                from bot.services.antiban import antiban_service
                antiban_service.mark_cookie_failed(cookie_file, str(e))
            raise

    async def _download_with_cookie_retry(self, url: str, format_id: str, max_size_mb: int, 
                                          is_audio: bool, file_uuid: str, ydl_base_opts: dict, 
                                          max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Download with automatic cookie retry on failure"""
        from bot.services.antiban import antiban_service
        
        retries = 0
        last_error = None
        attempted_cookies = set()
        
        while retries < max_retries:
            try:
                # Get next cookie (skip recently failed ones)
                cookie_file = antiban_service.get_random_cookie_file()
                
                if cookie_file == None:
                    break
                
                # Avoid trying the same cookie twice in a row
                if cookie_file in attempted_cookies and len(antiban_service.cookie_manager.all_cookies) > 1:
                    continue
                
                attempted_cookies.add(cookie_file)
                
                # Prepare options with cookie
                ydl_opts = dict(ydl_base_opts)
                if cookie_file and os.path.exists(cookie_file):
                    ydl_opts['cookiefile'] = cookie_file
                
                proxy = antiban_service.get_random_proxy()
                if proxy: 
                    ydl_opts['proxy'] = proxy
                
                logger.info(f"Download attempt {retries + 1} with cookie: {cookie_file}")
                
                # Try download
                loop = asyncio.get_event_loop()
                download_info = await loop.run_in_executor(
                    None, 
                    lambda: self._perform_download(url, ydl_opts, cookie_file)
                )
                
                if download_info:
                    # Download successful - return file info
                    preferred_ext = "mp3" if is_audio else "mp4"
                    filename = os.path.join(self.download_dir, f"{file_uuid}.{preferred_ext}")
                    if not os.path.exists(filename):
                        for f in os.listdir(self.download_dir):
                            if f.startswith(file_uuid):
                                filename = os.path.join(self.download_dir, f)
                                break
                    
                    if os.path.exists(filename):
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
                            'is_audio': is_audio
                        }
                
                return None
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Download attempt {retries + 1} failed: {last_error}")
                retries += 1
                
                # Reset limited failed cookies after all attempts to allow retry
                if retries >= max_retries:
                    antiban_service.cookie_manager.reset_failed_cookies()
        
        return {"error": f"Download failed after {retries} attempts. Last error: {last_error}"}

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

        # Use new retry logic with automatic cookie rotation
        return await self._download_with_cookie_retry(
            url=url,
            format_id=None,
            max_size_mb=max_size_mb,
            is_audio=False,
            file_uuid=file_uuid,
            ydl_base_opts=ydl_opts,
            max_retries=3
        )

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
