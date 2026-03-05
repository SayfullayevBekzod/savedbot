from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from bot.config import config
import time

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
        # Allow admins to bypass rate limits.
        if user_id in config.ADMIN_IDS:
            return await handler(event, data)

        # Never rate-limit critical bootstrap commands.
        if isinstance(event, Message):
            text = (event.text or "").strip().lower()
            if text.startswith("/start") or text.startswith("/lang"):
                return await handler(event, data)

        key = f"rl:{user_id}"
        
        last_request = await self.redis.get(key)
        now = time.time()
        
        if last_request:
            elapsed = now - float(last_request)
            if elapsed < self.cooldown:
                if isinstance(event, Message):
                    # Notify user only once per cooldown block to prevent spamming warnings
                    warned_key = f"rl_warn:{user_id}"
                    has_warned = await self.redis.get(warned_key)
                    if not has_warned:
                        await event.answer("⚠️ Iltimos, sekinroq yozing. (Spam himoyasi)")
                        await self.redis.set(warned_key, "1", ex=self.cooldown * 2)
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Sekinroq bosing.", show_alert=True)
                return

        await self.redis.set(key, str(now), ex=self.cooldown)
        return await handler(event, data)
