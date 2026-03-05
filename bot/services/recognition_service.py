import hashlib
import json
import logging
from typing import Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class RecognitionResult:
    """Structured recognition result."""
    title: str
    artist: str
    album: Optional[str] = None
    year: Optional[str] = None
    cover_url: Optional[str] = None
    lyrics: Optional[str] = None
    spotify_url: Optional[str] = None
    youtube_url: Optional[str] = None
    apple_music_url: Optional[str] = None
    shazam_url: Optional[str] = None
    audio_file_id: Optional[str] = None
    match_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RecognitionResult":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class RecognitionService:
    """Music recognition service (disabled for deployment)."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.cache_ttl = 86400  # 24 hours

    def set_redis(self, redis_client):
        self.redis = redis_client

    def _get_audio_hash(self, file_path: str) -> str:
        """Generate SHA256 hash of audio file for cache key."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    async def get_cached_result(self, audio_hash: str) -> Optional[RecognitionResult]:
        """Check Redis for cached recognition result."""
        if not self.redis:
            return None
        try:
            val = await self.redis.get(f"recognition:{audio_hash}")
            if val:
                data = json.loads(val)
                logger.info(f"Recognition HIT (Redis) for {audio_hash[:12]}...")
                return RecognitionResult.from_dict(data)
        except Exception as e:
            logger.error(f"Redis recognition cache error: {e}")
        return None

    async def cache_result(self, audio_hash: str, result: RecognitionResult):
        """Save result to Redis cache."""
        if not self.redis:
            return
        try:
            await self.redis.set(
                f"recognition:{audio_hash}",
                json.dumps(result.to_dict()),
                ex=self.cache_ttl
            )
            logger.info(f"Recognition SAVED (Redis) for {audio_hash[:12]}...")
        except Exception as e:
            logger.error(f"Redis recognition save error: {e}")

    async def recognize(self, file_path: str) -> Optional[RecognitionResult]:
        """
        Recognition disabled for deployment.
        Returns None for all requests.
        """
        logger.info("Music recognition disabled for deployment")
        return None

recognition_service = RecognitionService()
