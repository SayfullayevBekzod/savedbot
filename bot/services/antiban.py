import random
import os
import logging
from typing import Optional, List, Dict, Set
from bot.config import config
import time

logger = logging.getLogger(__name__)

class CookieManager:
    """Manages cookies with sequential rotation and failure tracking."""
    
    def __init__(self):
        self.all_cookies: List[str] = []
        self.cookie_status: Dict[str, Dict] = {}  # {cookie_path: {failed: bool, fail_count: int, last_used: time}}
        self._rotation_index: int = 0
        self._refresh_cookies()
        
    def _refresh_cookies(self):
        """Refresh the list of available cookies, prioritizing cookies.txt"""
        new_cookies = []
        
        # Priority 1: cookies.txt (if exists)
        if os.path.exists("cookies.txt"):
            new_cookies.append("cookies.txt")
        
        # Priority 2: cookies from cookies/ directory
        if os.path.exists("cookies/"):
            for f in sorted(os.listdir("cookies/")):
                if f.lower().endswith(".txt"):
                    cookie_path = os.path.join("cookies/", f)
                    if cookie_path not in new_cookies:
                        new_cookies.append(cookie_path)
        
        # Update the list
        self.all_cookies = new_cookies
        current_status = self.cookie_status
        self.cookie_status = {c: current_status[c] for c in self.all_cookies if c in current_status}
        
        # Initialize status for new cookies
        for cookie in self.all_cookies:
            if cookie not in self.cookie_status:
                self.cookie_status[cookie] = {
                    'failed': False,
                    'fail_count': 0,
                    'last_used': None,
                    'last_error': None
                }

        if self.all_cookies:
            self._rotation_index %= len(self.all_cookies)
        else:
            self._rotation_index = 0

    def _get_rotation_order(self) -> List[str]:
        """Return cookies ordered from current rotation pointer."""
        if not self.all_cookies:
            return []

        total = len(self.all_cookies)
        return [self.all_cookies[(self._rotation_index + i) % total] for i in range(total)]
    
    def get_next_cookie(self, exclude_failed: bool = True, attempted: Optional[Set[str]] = None) -> Optional[str]:
        """
        Get next cookie to use in round-robin order.
        If exclude_failed=True, tries working cookies first, then failed ones.
        Attempted cookies can be excluded for the current retry cycle.
        """
        self._refresh_cookies()  # Check for new cookies
        
        if not self.all_cookies:
            return None

        attempted = attempted or set()
        ordered = self._get_rotation_order()

        # First, try cookies that are not failed and not yet attempted
        candidates: List[str] = []
        if exclude_failed:
            candidates = [
                c for c in ordered
                if not self.cookie_status[c].get('failed', False) and c not in attempted
            ]

            # If all working cookies are exhausted, allow failed ones too
            if not candidates:
                candidates = [c for c in ordered if c not in attempted]
        else:
            candidates = [c for c in ordered if c not in attempted]

        if candidates:
            selected = candidates[0]
            selected_index = self.all_cookies.index(selected)
            self._rotation_index = (selected_index + 1) % len(self.all_cookies)
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
            self.cookie_status[cookie_path]['last_error'] = None
            logger.info(f"Cookie marked as working: {cookie_path}")
    
    def reset_failed_cookies(self):
        """Reset failed cookies to allow retry."""
        for cookie in self.cookie_status:
            if self.cookie_status[cookie]['fail_count'] > 0:
                # Reset after 5 attempts
                if self.cookie_status[cookie]['fail_count'] >= 5:
                    fail_count = self.cookie_status[cookie]['fail_count']
                    self.cookie_status[cookie]['failed'] = False
                    self.cookie_status[cookie]['fail_count'] = 0
                    logger.info(f"Cookie reset after {fail_count} failures: {cookie}")
    
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
        """Backward-compatible alias for sequential cookie selection."""
        return self.get_next_cookie_file()

    def get_next_cookie_file(self, attempted_cookies: Optional[Set[str]] = None) -> Optional[str]:
        """Get next cookie file in round-robin order, skipping attempted ones."""
        return self.cookie_manager.get_next_cookie(attempted=attempted_cookies)
    
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
