import hashlib
import logging
import json
from typing import Optional
from dataclasses import dataclass
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from bot.database.models import ContentCache
from bot.database.session import async_session

logger = logging.getLogger(__name__)

@dataclass
class CachedVideo:
    """Lightweight cache result (no SQLAlchemy dependency)."""
    file_id: str
    platform: str
    title: Optional[str] = None

class CacheService:
    def __init__(self, redis_client=None):
        self.redis = redis_client

    def set_redis(self, redis_client):
        self.redis = redis_client

    def normalize_url(self, url: str) -> str:
        from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
        
        try:
            parsed = urlparse(url)
            host = parsed.netloc.lower()
            path = parsed.path.rstrip('/')
            
            # Platform specific normalization
            if "youtube.com" in host or "youtu.be" in host:
                qs = dict(parse_qsl(parsed.query))
                if "v" in qs:
                    return f"https://www.youtube.com/watch?v={qs['v']}"
                if host == "youtu.be":
                    return f"https://www.youtube.com/watch?v={path.lstrip('/')}"
            
            if "instagram.com" in host:
                # Keep only /reels/ID or /p/ID or /tv/ID
                parts = path.split('/')
                if len(parts) >= 3 and parts[1] in ['reels', 'p', 'tv', 'reel']:
                    return f"https://www.instagram.com/{parts[1]}/{parts[2]}"
            
            if "tiktok.com" in host:
                # Strip everything after the ID
                if "/video/" in path:
                    video_id = path.split("/video/")[1].split('?')[0]
                    return f"https://www.tiktok.com/video/{video_id}"
                return f"https://{host}{path}" # Simplified for mobile links

            # Generic: Strip all tracking params (igsh, utm_, s, t, etc)
            qs = dict(parse_qsl(parsed.query))
            clean_qs = {k: v for k, v in qs.items() if not k.startswith(('utm_', 'igsh', 's', 't', '_', 'fbclid'))}
            
            return urlunparse(parsed._replace(
                query=urlencode(clean_qs),
                fragment=""
            )).rstrip('/')
        except Exception as e:
            logger.error(f"Normalization error: {e}")
            return url

    def get_url_hash(self, url: str) -> str:
        normalized = self.normalize_url(url)
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def get_cached_file(self, url: str) -> Optional[CachedVideo]:
        """
        Returns CachedVideo if found in Redis or DB.
        Redis = instant (< 1ms), DB = fallback (< 50ms).
        """
        url_hash = self.get_url_hash(url)
        
        # 1. Redis Speed-Lookup
        if self.redis:
            try:
                val = await self.redis.get(f"cache:{url_hash}")
                if val:
                    data = json.loads(val)
                    logger.info(f"Cache HIT (Redis) for {url_hash[:12]}...")
                    return CachedVideo(
                        file_id=data["file_id"],
                        platform=data.get("platform", "Unknown"),
                        title=data.get("title")
                    )
            except Exception as e:
                logger.error(f"Redis cache read error: {e}")

        # 2. Database Fallback
        try:
            async with async_session() as session:
                stmt = select(ContentCache).where(ContentCache.url_hash == url_hash)
                result = await session.execute(stmt)
                entry = result.scalar_one_or_none()
                
                if entry:
                    logger.info(f"Cache HIT (DB) for {url_hash[:12]}...")
                    # Warm Redis cache for next time
                    if self.redis:
                        data = {
                            "file_id": entry.file_id,
                            "platform": entry.platform,
                            "title": entry.title
                        }
                        await self.redis.set(f"cache:{url_hash}", json.dumps(data), ex=604800)
                    
                    return CachedVideo(
                        file_id=entry.file_id,
                        platform=entry.platform,
                        title=entry.title
                    )
        except Exception as e:
            logger.error(f"DB cache lookup error: {e}")
        
        logger.info(f"Cache MISS for {url_hash[:12]}...")
        return None

    async def set_cache(self, url: str, file_id: str, platform: str, title: Optional[str] = None):
        url_hash = self.get_url_hash(url)
        
        # Save to DB
        async with async_session() as session:
            try:
                cache_entry = ContentCache(
                    url_hash=url_hash,
                    file_id=file_id,
                    platform=platform,
                    title=title
                )
                session.add(cache_entry)
                await session.commit()
                logger.info(f"Cache SAVED (DB) for {url_hash[:12]}...")
            except IntegrityError:
                await session.rollback()
                logger.info(f"Cache already exists (DB) for {url_hash[:12]}...")
            except Exception as e:
                logger.error(f"Cache save error: {e}")
                await session.rollback()
        
        # Save to Redis
        if self.redis:
            try:
                data = {"file_id": file_id, "platform": platform, "title": title}
                await self.redis.set(f"cache:{url_hash}", json.dumps(data), ex=604800)
                logger.info(f"Cache SAVED (Redis) for {url_hash[:12]}...")
            except Exception as e:
                logger.error(f"Redis cache save error: {e}")

    async def cleanup_expired_cache(self, days: int = 30):
        async with async_session() as session:
            try:
                threshold = datetime.now() - timedelta(days=days)
                stmt = delete(ContentCache).where(ContentCache.created_at < threshold)
                await session.execute(stmt)
                await session.commit()
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
                await session.rollback()

cache_service = CacheService()
