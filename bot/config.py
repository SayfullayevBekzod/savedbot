from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional, List, Union

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: Union[List[int], int, str] = []
    SPONSOR_CHANNELS: List[str] = ["@Bekcode"] # Placeholder channel
    ENABLE_SUBSCRIPTION_CHECK: bool = False
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://bot_user:bot_password@db:5432/bot_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
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
