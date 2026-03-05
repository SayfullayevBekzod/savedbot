import os
import re
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional, List, Union


def normalize_redis_url(value):
    if not isinstance(value, str):
        return value

    url = value.strip().strip("\"'")
    if not url:
        return url

    replacements = {
        "redis://https://": "rediss://",
        "rediss://https://": "rediss://",
        "redis://http://": "redis://",
        "rediss://http://": "redis://",
        "redis://https:": "rediss://",
        "rediss://https:": "rediss://",
        "redis://http:": "redis://",
        "rediss://http:": "redis://",
        "https://": "rediss://",
        "http://": "redis://",
    }
    for bad_prefix, good_prefix in replacements.items():
        if url.startswith(bad_prefix):
            return good_prefix + url[len(bad_prefix):]

    malformed_patterns = [
        (r"^(?:redis|rediss)://(?P<auth>[^@/]+@)https://(?P<rest>.+)$", "rediss"),
        (r"^(?:redis|rediss)://(?P<auth>[^@/]+@)https:(?P<rest>.+)$", "rediss"),
        (r"^(?:redis|rediss)://(?P<auth>[^@/]+@)http://(?P<rest>.+)$", "redis"),
        (r"^(?:redis|rediss)://(?P<auth>[^@/]+@)http:(?P<rest>.+)$", "redis"),
        (r"^(?:redis|rediss)://https://(?P<rest>.+)$", "rediss"),
        (r"^(?:redis|rediss)://https:(?P<rest>.+)$", "rediss"),
        (r"^(?:redis|rediss)://http://(?P<rest>.+)$", "redis"),
        (r"^(?:redis|rediss)://http:(?P<rest>.+)$", "redis"),
    ]
    for pattern, scheme in malformed_patterns:
        match = re.match(pattern, url)
        if not match:
            continue
        auth = match.groupdict().get("auth", "")
        rest = match.group("rest").lstrip("/")
        return f"{scheme}://{auth}{rest}"

    return url


def normalize_webhook_host(value):
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    clean_render = None
    if isinstance(render_url, str):
        clean_render = render_url.strip().strip("\"'").rstrip("/")
        if clean_render and not clean_render.startswith(("http://", "https://")):
            clean_render = f"https://{clean_render}"

    if isinstance(value, str):
        result = value.strip().strip("\"'").rstrip("/")
        if result and not result.startswith(("http://", "https://")):
            result = f"https://{result}"
        if not result:
            return clean_render or None
        if clean_render and ".onrender.com" in result and ".onrender.com" in clean_render and result != clean_render:
            return clean_render
        return result

    if clean_render:
        return clean_render

    return value

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: Union[List[int], int, str] = []
    SPONSOR_CHANNELS: List[str] = ["@Bekcode"] # Placeholder channel
    ENABLE_SUBSCRIPTION_CHECK: bool = False
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://bot_user:bot_password@db:5432/bot_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""
    
    # Webhook
    WEBHOOK_HOST: Optional[str] = None
    WEBHOOK_PATH: str = "/webhook"
    BACKEND_PORT: int = 8000
    
    # App Settings
    DOWNLOAD_DIR: str = "downloads"
    
    # Video handling
    MAX_VIDEO_SIZE_MB: int = 50 # Telegram limit for bots
    AUTO_VIDEO_MAX_HEIGHT: int = 480  # Lower default height for fastest download
    UPLOAD_CHUNK_SIZE_KB: int = 4096  # 4MB chunks for maximum upload speed
    DOWNLOAD_CONCURRENT_FRAGMENTS: int = 256  # Maximum parallel fragments
    
    # Anti-ban
    COOLDOWN_SECONDS: int = 0  # No cooldown for maximum speed
    MAX_CONCURRENT_DOWNLOADS: int = 8  # Maximum concurrent downloads
    
    # Arq Settings
    ARQ_REDIS_URL: str = "redis://localhost:6379/1"

    @field_validator("REDIS_URL", "ARQ_REDIS_URL", mode="before")
    @classmethod
    def validate_redis_url(cls, v):
        return normalize_redis_url(v)

    @field_validator("WEBHOOK_HOST", mode="before")
    @classmethod
    def validate_webhook_host(cls, v):
        return normalize_webhook_host(v)
    
    @field_validator('ADMIN_IDS', mode='before')
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, list):
            return v
        elif isinstance(v, int):
            return [v]
        elif isinstance(v, str):
            # Handle comma-separated string or JSON-like string
            v = v.strip()
            if v.startswith('[') and v.endswith(']'):
                # Remove brackets and split
                v = v[1:-1]
            if ',' in v:
                return [int(id.strip()) for id in v.split(',') if id.strip()]
            elif v:
                return [int(v)]
        return []
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

config = Settings()
