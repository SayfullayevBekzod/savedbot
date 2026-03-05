from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: List[int] = []
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
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

config = Settings()
