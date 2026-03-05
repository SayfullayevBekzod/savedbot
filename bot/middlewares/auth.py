import json
import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from bot.database.session import async_session, Database
from bot.database.models import User

logger = logging.getLogger(__name__)

class AuthMiddleware(BaseMiddleware):
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not hasattr(event, "from_user") or event.from_user is None:
            return await handler(event, data)

        telegram_user = event.from_user
        user_id = telegram_user.id
        
        # 1. Try Redis Cache
        user_data = None
        if self.redis:
            val = await self.redis.get(f"user:{user_id}")
            if val:
                try:
                    user_data = json.loads(val)
                except Exception:
                    logger.error(f"Failed to parse user data from Redis for {user_id}")

        async with async_session() as session:
            db = Database(session)
            data["db"] = db
            
            user = None
            if user_data:
                try:
                    # User object from cache (not attached to session)
                    user = User(
                        id=user_data["id"],
                        username=user_data.get("username"),
                        full_name=user_data.get("full_name"),
                        role=user_data.get("role", "user"),
                        language=user_data.get("language", "uz"),
                        is_blocked=user_data.get("is_blocked", False),
                        referral_count=user_data.get("referral_count", 0)
                    )
                except Exception:
                    logger.warning(f"Failed to rebuild user from Redis for {user_id}")
                    user_data = None
            
            if not user:
                user = await db.get_user(user_id)
                
                if not user:
                    referred_by = None
                    if isinstance(event, Message) and event.text and event.text.startswith("/start "):
                        args = event.text.split(" ")
                        if len(args) > 1 and args[1].isdigit():
                            start_param = args[1]
                            referrer_id = int(start_param)
                            if referrer_id != telegram_user.id:
                                # Ensure referrer exists to avoid FK violation
                                referrer_exists = await db.get_user(referrer_id) # Assuming get_user can take ID
                                if referrer_exists:
                                    referred_by = referrer_id
                                    logger.info(f"User {telegram_user.id} referred by {referrer_id}")
                                else:
                                    logger.warning(f"Invalid referrer ID {referrer_id} for user {telegram_user.id}")

                    user = await db.create_user(
                        user_id=user_id,
                        username=telegram_user.username,
                        full_name=telegram_user.full_name,
                        referred_by=referred_by
                    )

                    if self.redis:
                        user_dict = {
                            "id": user.id,
                            "username": user.username,
                            "full_name": user.full_name,
                            "role": user.role,
                            "language": user.language,
                            "is_blocked": user.is_blocked,
                            "referral_count": user.referral_count
                        }
                        await self.redis.set(f"user:{user_id}", json.dumps(user_dict), ex=600)
            
            if user.is_blocked:
                if isinstance(event, Message):
                    await event.answer("🚫 Siz botdan foydalanishdan chetlatilgansiz.")
                return

            data["user"] = user
            return await handler(event, data)
