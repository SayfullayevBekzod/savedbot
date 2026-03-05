from datetime import datetime, date
from sqlalchemy import BigInteger, DateTime, Date, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import enum
from typing import Optional

class Base(DeclarativeBase):
    pass

class UserRole(enum.Enum):
    USER = "user"
    ADMIN = "admin"



class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default=UserRole.USER.value)
    subscription: Mapped[str] = mapped_column(String, default="free")
    premium_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Referral system
    referral_code: Mapped[str] = mapped_column(String, unique=True, nullable=True)
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Usage limits
    daily_downloads: Mapped[int] = mapped_column(Integer, default=0)
    last_download_date: Mapped[date] = mapped_column(Date, default=date.today)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    language: Mapped[str] = mapped_column(String, default="uz")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_premium: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)

    # Referrals tracking
    referral_count: Mapped[int] = mapped_column(Integer, default=0)

class Download(Base):
    __tablename__ = "downloads"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    platform: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    file_id: Mapped[Optional[str]] = mapped_column(String, nullable=True) # Telegram file_id for caching
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ContentCache(Base):
    __tablename__ = "content_cache"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_hash: Mapped[str] = mapped_column(String, index=True, unique=True)
    file_id: Mapped[str] = mapped_column(String)
    platform: Mapped[str] = mapped_column(String)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Recognition(Base):
    __tablename__ = "recognitions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String)
    artist: Mapped[str] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class SponsorChannel(Base):
    __tablename__ = "sponsor_channels"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String, unique=True)
    title: Mapped[str] = mapped_column(String)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    invite_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ScrapedContent(Base):
    __tablename__ = "scraped_content"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String, unique=True, index=True)
    media_url: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String) # reel, post, story
    username: Mapped[str] = mapped_column(String, index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    origin_timestamp: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
