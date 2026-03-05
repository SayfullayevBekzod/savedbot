import random
import os
import logging
from typing import Optional, List
from bot.config import config

class AntiBanService:
    def __init__(self):
        self.proxies: List[str] = self._load_proxies()
        self.cookie_files: List[str] = self._load_cookies()

    def _load_proxies(self) -> List[str]:
        # Expecting a file proxies.txt with one proxy per line
        if os.path.exists("proxies.txt"):
            with open("proxies.txt", "r") as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def _load_cookies(self) -> List[str]:
        # Expecting a directory 'cookies/' with multiple .txt cookie files
        if os.path.exists("cookies/"):
            return [os.path.join("cookies/", f) for f in os.listdir("cookies/") if f.endswith(".txt")]
        # Fallback to the default cookies.txt
        if os.path.exists("cookies.txt"):
            return ["cookies.txt"]
        return []

    def get_random_proxy(self) -> Optional[str]:
        if self.proxies:
            return random.choice(self.proxies)
        return None

    def get_random_cookie_file(self) -> Optional[str]:
        if self.cookie_files:
            return random.choice(self.cookie_files)
        return None

antiban_service = AntiBanService()
