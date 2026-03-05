import logging
import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger("bot.request")

class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        start_time = time.time()
        user_id = "unknown"
        if hasattr(event, "from_user") and event.from_user:
            user_id = event.from_user.id

        update_type = event.__class__.__name__
        logger.info(f"Update {update_type} from {user_id} started")

        try:
            result = await handler(event, data)
            duration = time.time() - start_time
            logger.info(f"Update {update_type} from {user_id} completed in {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Update {update_type} from {user_id} failed after {duration:.3f}s: {e}", exc_info=True)
            
            # User-friendly error message if it's a message event
            if isinstance(event, Message):
                await event.answer("⚠️ Kutilmagan xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring yoki admin bilan bog'laning.")
            
            raise e
