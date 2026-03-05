import yt_dlp
import os
import asyncio
from typing import Optional

class Downloader:
    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    async def download_media(self, url: str) -> Optional[dict]:
        """
        Downloads media and returns a dictionary with file_path and info.
        """
        # Define output template for the filename
        outtmpl = os.path.join(self.download_dir, '%(title)s.%(ext)s')
        
        # Format selection:
        # 1. Try to get best video + best audio (up to 4K)
        # 2. Limit to 50MB for Telegram bots (we will check size before downloading)
        ydl_opts = {
            'format': 'bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': outtmpl,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
            'concurrent_fragment_downloads': 10, # Multi-threaded downloading
            'noprogress': True,
        }

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: self._extract_info(url))
            
            if not info:
                return None

            # Check file size if available before downloading
            filesize = info.get('filesize_approx') or info.get('filesize')
            if filesize and filesize > 50 * 1024 * 1024:
                # If too large, try to find a smaller format (720p or 480p)
                ydl_opts['format'] = 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best'
            
            # Perform actual download
            download_info = await loop.run_in_executor(None, lambda: self._download(url, ydl_opts))
            
            if download_info:
                filename = yt_dlp.YoutubeDL(ydl_opts).prepare_filename(download_info)
                # Ensure the file exists (yt-dlp might change extension)
                if not os.path.exists(filename):
                     base, _ = os.path.splitext(filename)
                     if os.path.exists(base + ".mp4"):
                         filename = base + ".mp4"
                     else:
                        # Fallback search
                        title = download_info.get('title', 'video')
                        for file in os.listdir(self.download_dir):
                            if title in file and file.endswith('.mp4'):
                                filename = os.path.join(self.download_dir, file)
                                break
                
                return {
                    'file_path': filename,
                    'title': download_info.get('title', 'Video'),
                    'filesize': os.path.getsize(filename) if os.path.exists(filename) else 0
                }
            return None
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return None

    def _extract_info(self, url: str):
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            return ydl.extract_info(url, download=False)

    def _download(self, url: str, opts: dict):
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

downloader = Downloader()
