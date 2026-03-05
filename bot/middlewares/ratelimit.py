import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import config

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, redis_client):
        self.redis = redis_client
        self.cooldown = config.COOLDOWN_SECONDS

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        if not self.redis:
            return await handler(event, data)

        user_id = event.from_user.id
        if user_id in config.ADMIN_IDS:
            return await handler(event, data)

        if isinstance(event, Message):
            text = (event.text or "").strip().lower()
            if text.startswith("/start") or text.startswith("/lang"):
                return await handler(event, data)

        key = f"rl:{user_id}"
        try:
            last_request = await self.redis.get(key)
        except Exception as e:
            logger.warning(f"RateLimit Redis read error: {e}")
            return await handler(event, data)

        now = time.time()
        if last_request:
            elapsed = now - float(last_request)
            if elapsed < self.cooldown:
                if isinstance(event, Message):
                    warned_key = f"rl_warn:{user_id}"
                    try:
                        has_warned = await self.redis.get(warned_key)
                    except Exception as e:
                        logger.warning(f"RateLimit warn-check Redis error: {e}")
                        has_warned = None

                    if not has_warned:
                        await event.answer("Iltimos, sekinroq yozing. (Spam himoyasi)")
                        try:
                            await self.redis.set(warned_key, "1", ex=self.cooldown * 2)
                        except Exception as e:
                            logger.warning(f"RateLimit warn-set Redis error: {e}")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Sekinroq bosing.", show_alert=True)
                return

        try:
            await self.redis.set(key, str(now), ex=self.cooldown)
        except Exception as e:
            logger.warning(f"RateLimit Redis write error: {e}")

        return await handler(event, data)
