import aiohttp
import asyncio
import logging
import json
from typing import List, Dict, Any, Optional

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class InstagramScraper:
    """
    RapidAPI Instagram Scraper Stable API orqali ma'lumotlarni olish klassi.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://instagram-scraper-stable-api.p.rapidapi.com"
        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "instagram-scraper-stable-api.p.rapidapi.com",
            "Content-Type": "application/x-www-form-urlencoded"
        }

    async def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        API ga async so'rov yuborish uchun ichki funksiya.
        """
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, data=data, headers=self.headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        text = await response.text()
                        logger.error(f"API xatosi: {response.status} - {text}")
                        return {}
            except Exception as e:
                logger.exception(f"So'rov yuborishda xatolik: {e}")
                return {}

    def _parse_item(self, item: Dict[str, Any], item_type: str) -> Dict[str, Any]:
        """
        API natijasini standart formatga keltirish.
        """
        # API dan keladigan maydonlar o'zgarishi mumkin, shuning uchun xavfsiz olish
        return {
            "url": f"https://www.instagram.com/reels/{item.get('shortcode')}/" if item_type == "reel" else f"https://www.instagram.com/p/{item.get('shortcode')}/",
            "media_url": item.get("video_url") or item.get("display_url"),
            "type": item_type,
            "username": item.get("owner", {}).get("username") or "unknown",
            "timestamp": item.get("taken_at_timestamp")
        }

    async def get_user_reels(self, username: str, max_pages: int = 1, db: Any = None) -> List[Dict[str, Any]]:
        """
        1. Foydalanuvchi barcha Reels larini olish.
        """
        logger.info(f"@{username} uchun Reels qidirilmoqda...")
        results = []
        pagination_token = ""
        
        for page in range(max_pages):
            data = {"username": username}
            if pagination_token:
                data["pagination_token"] = pagination_token
            
            resp = await self._make_request("/get_ig_user_reels.php", data)
            items = resp.get("data", {}).get("items", [])
            
            for item in items:
                parsed = self._parse_item(item, "reel")
                results.append(parsed)
                if db:
                    await db.add_scraped_content(
                        url=parsed["url"],
                        media_url=parsed["media_url"],
                        content_type=parsed["type"],
                        username=parsed["username"],
                        origin_timestamp=parsed["timestamp"]
                    )
            
            logger.info(f"Sahifa {page+1}: {len(items)} ta Reels topildi.")
            
            pagination_token = resp.get("data", {}).get("pagination_token")
            if not pagination_token:
                break
            
            await asyncio.sleep(1) # Rate limit uchun 1 sek kutish
            
        logger.info(f"Jami @{username} uchun {len(results)} ta Reels topildi.")
        return results

    async def get_hashtag_posts(self, hashtag: str, max_pages: int = 1, db: Any = None) -> List[Dict[str, Any]]:
        """
        2. Hashtag bo'yicha postlarni olish.
        """
        logger.info(f"#{hashtag} uchun postlar qidirilmoqda...")
        results = []
        pagination_token = ""
        
        for page in range(max_pages):
            data = {"hashtag": hashtag}
            if pagination_token:
                data["pagination_token"] = pagination_token
            
            resp = await self._make_request("/get_ig_hashtag_posts.php", data)
            items = resp.get("data", {}).get("items", [])
            
            for item in items:
                parsed = self._parse_item(item, "post")
                results.append(parsed)
                if db:
                    await db.add_scraped_content(
                        url=parsed["url"],
                        media_url=parsed["media_url"],
                        content_type=parsed["type"],
                        username=parsed["username"],
                        origin_timestamp=parsed["timestamp"]
                    )
                
            logger.info(f"Sahifa {page+1}: {len(items)} ta hashtag posti topildi.")
            
            pagination_token = resp.get("data", {}).get("pagination_token")
            if not pagination_token:
                break
            
            await asyncio.sleep(1)
            
        logger.info(f"Jami #{hashtag} uchun {len(results)} ta post topildi.")
        return results

    async def get_user_stories(self, username: str, db: Any = None) -> List[Dict[str, Any]]:
        """
        3. Foydalanuvchi Stories larini olish (Odatda story-larda pagination bo'lmaydi).
        """
        logger.info(f"@{username} uchun Stories qidirilmoqda...")
        results = []
        
        resp = await self._make_request("/get_ig_user_stories.php", {"username": username})
        items = resp.get("data", {}).get("items", [])
        
        for item in items:
            parsed = self._parse_item(item, "story")
            results.append(parsed)
            if db:
                await db.add_scraped_content(
                    url=parsed["url"],
                    media_url=parsed["media_url"],
                    content_type=parsed["type"],
                    username=parsed["username"],
                    origin_timestamp=parsed["timestamp"]
                )
            
        logger.info(f"@{username} uchun {len(results)} ta Story topildi.")
        return results

    async def get_user_posts(self, username: str, max_pages: int = 1, db: Any = None) -> List[Dict[str, Any]]:
        """
        4. Foydalanuvchi barcha postlari + video linklarini olish.
        """
        logger.info(f"@{username} uchun barcha postlar qidirilmoqda...")
        results = []
        pagination_token = ""
        
        for page in range(max_pages):
            data = {"username": username}
            if pagination_token:
                data["pagination_token"] = pagination_token
            
            resp = await self._make_request("/get_ig_user_posts.php", data)
            items = resp.get("data", {}).get("items", [])
            
            for item in items:
                parsed = self._parse_item(item, "post")
                results.append(parsed)
                if db:
                    await db.add_scraped_content(
                        url=parsed["url"],
                        media_url=parsed["media_url"],
                        content_type=parsed["type"],
                        username=parsed["username"],
                        origin_timestamp=parsed["timestamp"]
                    )
                
            logger.info(f"Sahifa {page+1}: {len(items)} ta post topildi.")
            
            pagination_token = resp.get("data", {}).get("pagination_token")
            if not pagination_token:
                break
            
            await asyncio.sleep(1)
            
        logger.info(f"Jami @{username} uchun {len(results)} ta post topildi.")
        return results
