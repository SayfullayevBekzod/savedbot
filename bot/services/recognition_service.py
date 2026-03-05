import asyncio
import hashlib
import json
import logging
from typing import Optional
from dataclasses import dataclass, asdict
from shazamio import Shazam

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
    """Music recognition using Shazam (free, no API key)."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.shazam = Shazam()
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
            val = await self.redis.get(f"shazam:{audio_hash}")
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
                f"shazam:{audio_hash}",
                json.dumps(result.to_dict()),
                ex=self.cache_ttl
            )
            logger.info(f"Recognition SAVED (Redis) for {audio_hash[:12]}...")
        except Exception as e:
            logger.error(f"Redis recognition save error: {e}")

    def _extract_provider_url(self, provider: dict) -> Optional[str]:
        for action in provider.get("actions", []):
            url = action.get("uri") or action.get("url")
            if url:
                return url
        return None

    def _extract_track_metadata(self, track: dict) -> tuple[Optional[str], Optional[str]]:
        album = None
        year = None

        for section in track.get("sections", []):
            for meta in section.get("metadata", []) or []:
                title = (meta.get("title") or "").strip().lower()
                value = (meta.get("text") or "").strip()
                if not value:
                    continue

                if not album and title in {"album"}:
                    album = value

                if not year and (title in {"released", "year"} or value[:4].isdigit()):
                    year = value[:4] if value[:4].isdigit() else value

                if album and year:
                    return album, year
        return album, year

    async def recognize(self, file_path: str) -> Optional[RecognitionResult]:
        """
        Full recognition pipeline:
        1. Hash audio file
        2. Check Redis cache
        3. If miss → call Shazam API
        4. Parse and cache result
        """
        audio_hash = self._get_audio_hash(file_path)

        # 1. Cache check
        cached = await self.get_cached_result(audio_hash)
        if cached:
            return cached

        # 2. Call Shazam with retries for library stability
        for attempt in range(2):
            try:
                logger.info(f"Recognizing audio {audio_hash[:12]} (Attempt {attempt+1})...")
                # Use a small wait to avoid rapid-fire issues if it's a transient lib error
                if attempt > 0:
                    await asyncio.sleep(1)
                
                result = await self.shazam.recognize(file_path)

                if not result or "track" not in result:
                    logger.info("Shazam: No match found")
                    return None

                track = result["track"]
                album, year = self._extract_track_metadata(track)
                match_count = len(result.get("matches", []) or [])

                # 3. Extract links and lyrics
                spotify_url = None
                youtube_url = None
                apple_music_url = None
                lyrics = None

                for provider in track.get("hub", {}).get("providers", []):
                    ptype = provider.get("type", "").upper()
                    url = self._extract_provider_url(provider)
                    if not url:
                        continue
                    if ptype == "SPOTIFY":
                        spotify_url = url
                    elif ptype == "YOUTUBE":
                        youtube_url = url
                    elif ptype == "APPLEMUSIC":
                        apple_music_url = url

                # Extract Lyrics from sections
                for section in track.get("sections", []):
                    if section.get("type") == "LYRICS":
                        lyrics_lines = section.get("text", [])
                        if lyrics_lines:
                            lyrics = "\n".join(lyrics_lines)
                    elif section.get("type") == "SONG" and not apple_music_url:
                        for meta in section.get("metapages", []):
                            if "apple" in meta.get("caption", "").lower():
                                apple_music_url = meta.get("image")

                # Shazam URL
                shazam_url = track.get("url")

                recognition = RecognitionResult(
                    title=track.get("title", "Nomalum"),
                    artist=track.get("subtitle", "Nomalum"),
                    album=album,
                    year=year,
                    cover_url=(track.get("images", {}).get("coverarthq")
                               or track.get("images", {}).get("coverart")
                               or track.get("images", {}).get("background")),
                    lyrics=lyrics,
                    spotify_url=spotify_url,
                    youtube_url=youtube_url,
                    apple_music_url=apple_music_url,
                    shazam_url=shazam_url,
                    match_count=match_count,
                )

                # 4. Cache
                await self.cache_result(audio_hash, recognition)
                return recognition

            except Exception as e:
                logger.error(f"Shazam recognition error (Attempt {attempt+1}): {e}")
                if attempt == 1: # Last try
                    return None
        return None

recognition_service = RecognitionService()
