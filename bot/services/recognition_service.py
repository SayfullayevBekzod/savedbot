import hashlib
import json
import logging
import os
from typing import Optional, Any, Dict
from dataclasses import dataclass, asdict
from bot.config import config

logger = logging.getLogger(__name__)
# shazamio internals can emit excessive MP3 parser warnings for noisy inputs.
logging.getLogger("symphonia").setLevel(logging.ERROR)
logging.getLogger("symphonia_bundle_mp3").setLevel(logging.ERROR)
logging.getLogger("symphonia_bundle_mp3.demuxer").setLevel(logging.ERROR)

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
    """Music recognition service (Shazam-only)."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.cache_ttl = 86400  # 24 hours

        # ShazamIO only
        self.shazam_client = None
        try:
            from shazamio import Shazam
            self.shazam_client = Shazam()
            logger.info("Recognition provider initialized: shazamio")
        except Exception as e:
            logger.warning(f"shazamio unavailable: {e}")

    def set_redis(self, redis_client):
        self.redis = redis_client

    @staticmethod
    def _get_proxy() -> Optional[str]:
        """Get proxy for recognition requests (explicit config first)."""
        from bot.config import config as runtime_config

        explicit_proxy = (runtime_config.RECOGNITION_PROXY or "").strip()
        if explicit_proxy:
            return explicit_proxy

        try:
            from bot.services.antiban import antiban_service
            return antiban_service.get_random_proxy()
        except Exception:
            return None

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

    @staticmethod
    def _extract_shazam_cover(track: Dict[str, Any]) -> Optional[str]:
        images = track.get("images")
        if not isinstance(images, dict):
            return None
        return images.get("coverarthq") or images.get("coverart") or images.get("background")

    @staticmethod
    def _extract_shazam_url(track: Dict[str, Any]) -> Optional[str]:
        share = track.get("share")
        if isinstance(share, dict):
            href = share.get("href")
            if href:
                return href
        return track.get("url")

    @staticmethod
    def _extract_shazam_youtube(track: Dict[str, Any]) -> Optional[str]:
        sections = track.get("sections")
        if not isinstance(sections, list):
            return None

        for section in sections:
            if not isinstance(section, dict):
                continue
            stype = str(section.get("type") or "").upper()
            if stype == "VIDEO":
                return section.get("youtubeurl") or section.get("youtube_url") or section.get("url")
        return None

    @staticmethod
    def _extract_shazam_lyrics(track: Dict[str, Any]) -> Optional[str]:
        sections = track.get("sections")
        if not isinstance(sections, list):
            return None

        for section in sections:
            if not isinstance(section, dict):
                continue
            if str(section.get("type") or "").upper() != "LYRICS":
                continue
            text = section.get("text")
            if isinstance(text, list):
                lines = [str(line).strip() for line in text if str(line).strip()]
                return "\n".join(lines) if lines else None
            if isinstance(text, str):
                return text.strip() or None
        return None

    @staticmethod
    def _extract_shazam_album_year(track: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        album = None
        year = None

        sections = track.get("sections")
        if not isinstance(sections, list):
            return album, year

        for section in sections:
            if not isinstance(section, dict):
                continue
            if str(section.get("type") or "").upper() != "SONG":
                continue

            metadata = section.get("metadata")
            if not isinstance(metadata, list):
                continue

            for item in metadata:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip().lower()
                text = str(item.get("text") or "").strip()
                if not text:
                    continue

                if album is None and "album" in title:
                    album = text

                if year is None and ("released" in title or "year" in title):
                    digits = "".join(ch for ch in text if ch.isdigit())
                    year = digits[:4] if len(digits) >= 4 else text

        return album, year

    @staticmethod
    def _extract_uri_from_actions(actions: Any) -> Optional[str]:
        if not isinstance(actions, list):
            return None
        for action in actions:
            if not isinstance(action, dict):
                continue
            uri = action.get("uri") or action.get("url")
            if isinstance(uri, str) and uri.strip():
                return uri.strip()
        return None

    def _extract_shazam_links(self, track: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        spotify_url = None
        apple_music_url = None

        hub = track.get("hub")
        if not isinstance(hub, dict):
            return spotify_url, apple_music_url

        providers = hub.get("providers")
        if isinstance(providers, list):
            for provider in providers:
                if not isinstance(provider, dict):
                    continue
                p_type = str(provider.get("type") or "").upper()
                uri = self._extract_uri_from_actions(provider.get("actions"))

                if uri and spotify_url is None and "SPOTIFY" in p_type:
                    spotify_url = uri
                if uri and apple_music_url is None and "APPLE" in p_type:
                    apple_music_url = uri

        options = hub.get("options")
        if apple_music_url is None and isinstance(options, list):
            for option in options:
                if not isinstance(option, dict):
                    continue
                uri = self._extract_uri_from_actions(option.get("actions"))
                if uri and "music.apple.com" in uri:
                    apple_music_url = uri
                    break

        return spotify_url, apple_music_url

    async def _recognize_with_shazamio(self, file_path: str) -> Optional[RecognitionResult]:
        if not self.shazam_client:
            logger.warning("shazamio client is not available.")
            return None
        if not os.path.exists(file_path):
            logger.warning(f"Recognition file not found: {file_path}")
            return None

        payload: Optional[Dict[str, Any]] = None
        proxy = self._get_proxy()
        try:
            payload = await self.shazam_client.recognize(file_path, proxy=proxy)
        except Exception as e:
            # Fallback method does not require shazamio-core.
            logger.warning(f"shazamio recognize() failed, fallback to recognize_song(): {e}")
            try:
                payload = await self.shazam_client.recognize_song(file_path, proxy=proxy)
            except Exception as fallback_error:
                logger.error(f"shazamio fallback failed: {fallback_error}")
                return None

        if not isinstance(payload, dict):
            return None

        track = payload.get("track")
        if not isinstance(track, dict):
            return None

        title = str(track.get("title") or "").strip()
        artist = str(track.get("subtitle") or "").strip()
        if not title or not artist:
            return None

        album, year = self._extract_shazam_album_year(track)
        lyrics = self._extract_shazam_lyrics(track)
        youtube_url = self._extract_shazam_youtube(track)
        spotify_url, apple_music_url = self._extract_shazam_links(track)

        matches = payload.get("matches")
        match_count = len(matches) if isinstance(matches, list) else 0

        return RecognitionResult(
            title=title,
            artist=artist,
            album=album,
            year=year,
            cover_url=self._extract_shazam_cover(track),
            lyrics=lyrics,
            spotify_url=spotify_url,
            youtube_url=youtube_url,
            apple_music_url=apple_music_url,
            shazam_url=self._extract_shazam_url(track),
            match_count=match_count,
        )

    async def recognize(self, file_path: str) -> Optional[RecognitionResult]:
        """Recognize music from audio file and cache result."""
        try:
            audio_hash = self._get_audio_hash(file_path)
            cached = await self.get_cached_result(audio_hash)
            if cached:
                return cached

            result = await self._recognize_with_shazamio(file_path)
            if result:
                logger.info("Recognition success via provider: shazamio")

            if result:
                await self.cache_result(audio_hash, result)
            return result
        except Exception as e:
            logger.error(f"Recognition error: {e}")
            return None

recognition_service = RecognitionService()
