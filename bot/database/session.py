from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import asyncio
from datetime import date
import logging
from bot.config import config
from bot.database.models import Base, User, Download
from sqlalchemy import select, update, func
from typing import Optional
import uuid

logger = logging.getLogger(__name__)

# For Neon and other cloud providers requiring SSL
connect_args = {}
if "sslmode=require" in config.DATABASE_URL or "neon.tech" in config.DATABASE_URL:
    connect_args["ssl"] = True

engine = create_async_engine(
    config.DATABASE_URL.split("?")[0] if "sslmode" in config.DATABASE_URL else config.DATABASE_URL,
    connect_args=connect_args,
    pool_size=20,
    max_overflow=10,
    pool_recycle=3600
)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    try:
        async with asyncio.timeout(10):
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    except asyncio.TimeoutError:
        logger.warning("Database initialization timed out. Skipping create_all.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

class Database:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, user_id: int, username: Optional[str], full_name: Optional[str], referred_by: Optional[int] = None) -> User:
        ref_code = str(uuid.uuid4())[:8]
        user = User(
            id=user_id, 
            username=username, 
            full_name=full_name, 
            subscription="free",
            daily_downloads=0,
            last_download_date=date.today(),
            is_premium=False,
            referral_code=ref_code,
            referred_by=referred_by
        )
        self.session.add(user)
        
        # Increment referral count for inviter
        if referred_by:
            await self.session.execute(
                update(User).where(User.id == referred_by).values(referral_count=User.referral_count + 1)
            )
            
        await self.session.commit()
        return user

    async def set_user_block_status(self, user_id: int, is_blocked: bool):
        """Block or unblock a user."""
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_blocked=is_blocked)
        )
        await self.session.commit()

    async def set_user_language(self, user_id: int, language: str):
        """Update user language preference."""
        await self.session.execute(
            update(User).where(User.id == user_id).values(language=language)
        )
        await self.session.commit()

    async def increment_download(self, user_id: int, platform: str, url: str, file_id: Optional[str] = None):
        # 1. Add to downloads history
        download = Download(user_id=user_id, platform=platform, url=url, file_id=file_id)
        self.session.add(download)
        
        # 2. Commit the download
        await self.session.commit()

    async def get_stats(self):
        users_count = await self.session.scalar(select(func.count(User.id)))
        downloads_count = await self.session.scalar(select(func.count(Download.id)))
        return {"users": users_count, "downloads": downloads_count}

    async def get_detailed_stats(self):
        """More detailed statistics including daily active users and platform breakdown."""
        # 1. Platform stats
        platform_res = await self.session.execute(
            select(Download.platform, func.count(Download.id)).group_by(Download.platform)
        )
        platforms = {p: c for p, c in platform_res.all()}
        
        # 2. Daily growth (last 7 days)
        growth_res = await self.session.execute(
            select(func.date(User.joined_at), func.count(User.id))
            .group_by(func.date(User.joined_at))
            .order_by(func.date(User.joined_at).desc())
            .limit(7)
        )
        growth = {str(d): c for d, c in growth_res.all()}
        
        return {
            "platforms": platforms,
            "growth": growth
        }

    async def get_user_download_count(self, user_id: int) -> int:
        """Get total downloads for a specific user."""
        result = await self.session.execute(
            select(func.count(Download.id)).where(Download.user_id == user_id)
        )
        return result.scalar() or 0

    async def add_recognition_log(self, user_id: int, title: str, artist: str):
        from bot.database.models import Recognition
        log = Recognition(user_id=user_id, title=title, artist=artist)
        self.session.add(log)
        await self.session.commit()

    async def get_top_links(self, limit: int = 10):
        # Join with ContentCache to get titles if available
        result = await self.session.execute(
            select(Download.url, func.count(Download.id).label('count'))
            .group_by(Download.url)
            .order_by(func.count(Download.id).desc())
            .limit(limit)
        )
        return result.all()

    async def get_top_songs(self, limit: int = 10):
        from bot.database.models import Recognition
        result = await self.session.execute(
            select(Recognition.artist, Recognition.title, func.count(Recognition.id).label('count'))
            .group_by(Recognition.artist, Recognition.title)
            .order_by(func.count(Recognition.id).desc())
            .limit(limit)
        )
        return result.all()

    async def search_users(self, query: str, limit: int = 20):
        """Search users by ID, username, or full name."""
        stmt = select(User)
        if query.isdigit():
            stmt = stmt.where(User.id == int(query))
        else:
            q = f"%{query}%"
            stmt = stmt.where((User.username.ilike(q)) | (User.full_name.ilike(q)))
        
        result = await self.session.execute(stmt.limit(limit))
        return result.scalars().all()

    async def get_all_users(self):
        """Retrieve all users for export."""
        result = await self.session.execute(select(User).order_by(User.joined_at.asc()))
        return result.scalars().all()

    async def get_sponsor_channels(self):
        """Retrieve all mandatory channels."""
        from bot.database.models import SponsorChannel
        result = await self.session.execute(select(SponsorChannel).order_by(SponsorChannel.created_at.asc()))
        return result.scalars().all()

    async def add_sponsor_channel(self, channel_id: str, title: str, username: Optional[str] = None, invite_link: Optional[str] = None):
        """Add a new mandatory channel."""
        from bot.database.models import SponsorChannel
        channel = SponsorChannel(channel_id=channel_id, title=title, username=username, invite_link=invite_link)
        self.session.add(channel)
        await self.session.commit()
        return channel

    async def delete_sponsor_channel(self, channel_id: str):
        """Delete a mandatory channel."""
        from bot.database.models import SponsorChannel
        from sqlalchemy import delete
        await self.session.execute(delete(SponsorChannel).where(SponsorChannel.channel_id == channel_id))
        await self.session.commit()

    async def add_scraped_content(self, url: str, media_url: str, content_type: str, username: str, origin_timestamp: Optional[int] = None):
        """Add or update scraped content (Upsert)."""
        from bot.database.models import ScrapedContent
        from sqlalchemy.dialects.postgresql import insert
        
        stmt = insert(ScrapedContent).values(
            url=url,
            media_url=media_url,
            content_type=content_type,
            username=username,
            origin_timestamp=origin_timestamp
        ).on_conflict_do_update(
            index_elements=["url"],
            set_={
                "media_url": media_url,
                "scraped_at": datetime.utcnow()
            }
        )
        await self.session.execute(stmt)
        await self.session.commit()
