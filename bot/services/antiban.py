import random
import os
import logging
from typing import Optional, List, Dict
from bot.config import config
import time

logger = logging.getLogger(__name__)

class CookieManager:
    """Manages cookies with automatic rotation and failure tracking."""
    
    def __init__(self):
        self.all_cookies: List[str] = []
        self.cookie_status: Dict[str, Dict] = {}  # {cookie_path: {failed: bool, fail_count: int, last_used: time}}
        self._refresh_cookies()
        
    def _refresh_cookies(self):
        """Refresh the list of available cookies, prioritizing cookies.txt"""
        new_cookies = []
        
        # Priority 1: cookies.txt (if exists)
        if os.path.exists("cookies.txt"):
            new_cookies.append("cookies.txt")
        
        # Priority 2: cookies from cookies/ directory
        if os.path.exists("cookies/"):
            for f in os.listdir("cookies/"):
                if f.endswith(".txt"):
                    cookie_path = os.path.join("cookies/", f)
                    if cookie_path not in new_cookies:
                        new_cookies.append(cookie_path)
        
        # Update the list
        self.all_cookies = new_cookies
        
        # Initialize status for new cookies
        for cookie in self.all_cookies:
            if cookie not in self.cookie_status:
                self.cookie_status[cookie] = {
                    'failed': False,
                    'fail_count': 0,
                    'last_used': None,
                    'last_error': None
                }
    
    def get_next_cookie(self, exclude_failed: bool = True) -> Optional[str]:
        """
        Get next cookie to use.
        If exclude_failed=True, tries working cookies first, then retries failed ones.
        """
        self._refresh_cookies()  # Check for new cookies
        
        if not self.all_cookies:
            return None
        
        # First, try cookies that are not failed
        available = [c for c in self.all_cookies if not self.cookie_status[c].get('failed', False)]
        
        if available:
            cookie = random.choice(available)
            self.cookie_status[cookie]['last_used'] = time.time()
            return cookie
        
        # If all are failed, reset one and try it
        if self.all_cookies:
            selected = random.choice(self.all_cookies)
            self.cookie_status[selected]['last_used'] = time.time()
            return selected
        
        return None
    
    def mark_cookie_failed(self, cookie_path: str, error: str = None):
        """Mark a cookie as failed."""
        if cookie_path in self.cookie_status:
            self.cookie_status[cookie_path]['failed'] = True
            self.cookie_status[cookie_path]['fail_count'] += 1
            self.cookie_status[cookie_path]['last_error'] = error
            logger.warning(f"Cookie marked as failed: {cookie_path} (fails: {self.cookie_status[cookie_path]['fail_count']}) - {error}")
    
    def mark_cookie_working(self, cookie_path: str):
        """Mark a cookie as working."""
        if cookie_path in self.cookie_status:
            self.cookie_status[cookie_path]['failed'] = False
            self.cookie_status[cookie_path]['fail_count'] = 0
            logger.info(f"Cookie marked as working: {cookie_path}")
    
    def reset_failed_cookies(self):
        """Reset failed cookies to allow retry."""
        for cookie in self.cookie_status:
            if self.cookie_status[cookie]['fail_count'] > 0:
                # Reset after 5 attempts
                if self.cookie_status[cookie]['fail_count'] >= 5:
                    self.cookie_status[cookie]['failed'] = False
                    self.cookie_status[cookie]['fail_count'] = 0
                    logger.info(f"Cookie reset after {self.cookie_status[cookie]['fail_count']} failures: {cookie}")
    
    def get_status(self) -> Dict:
        """Get current status of all cookies."""
        return {
            'total_cookies': len(self.all_cookies),
            'working_cookies': len([c for c in self.all_cookies if not self.cookie_status[c].get('failed')]),
            'failed_cookies': len([c for c in self.all_cookies if self.cookie_status[c].get('failed')]),
            'cookies': {c: self.cookie_status[c] for c in self.all_cookies}
        }


class AntiBanService:
    def __init__(self):
        self.proxies: List[str] = self._load_proxies()
        self.cookie_manager = CookieManager()

    def _load_proxies(self) -> List[str]:
        # Expecting a file proxies.txt with one proxy per line
        if os.path.exists("proxies.txt"):
            with open("proxies.txt", "r") as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def get_random_proxy(self) -> Optional[str]:
        if self.proxies:
            return random.choice(self.proxies)
        return None

    def get_random_cookie_file(self) -> Optional[str]:
        """Get next cookie file (with automatic rotation on failure)."""
        return self.cookie_manager.get_next_cookie()
    
    def mark_cookie_failed(self, cookie_path: str, error: str = None):
        """Mark cookie as failed and use next one."""
        self.cookie_manager.mark_cookie_failed(cookie_path, error)
    
    def mark_cookie_working(self, cookie_path: str):
        """Mark cookie as working."""
        self.cookie_manager.mark_cookie_working(cookie_path)
    
    def get_cookie_status(self) -> Dict:
        """Get status of all cookies."""
        return self.cookie_manager.get_status()

antiban_service = AntiBanService()
