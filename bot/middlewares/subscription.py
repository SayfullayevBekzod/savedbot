from aiogram import BaseMiddleware, types
import asyncio
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot.utils.i18n import translator
from bot.config import config
import logging

logger = logging.getLogger(__name__)

class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not isinstance(event, (types.Message, types.CallbackQuery)):
            return await handler(event, data)

        # Allow disabling mandatory channel checks globally.
        if not config.ENABLE_SUBSCRIPTION_CHECK:
            return await handler(event, data)

        user = data.get("user")
        if not user or user.role == "admin":
            return await handler(event, data)

        # Allow /start command to pass so users get the welcome message
        if isinstance(event, types.Message) and event.text and event.text.startswith("/start"):
            return await handler(event, data)

        # Allow language selection callback to pass
        if isinstance(event, types.CallbackQuery) and event.data and event.data.startswith("setlang:"):
            return await handler(event, data)

        # Check subscription
        bot = data['bot']
        redis = data.get("redis_client")
        
        # 1. Try Cache
        if redis:
            cached_sub = await redis.get(f"sub_checked:{user.id}")
            if cached_sub:
                return await handler(event, data)

        # 2. Get channels from DB
        from bot.database.session import async_session, Database
        async with async_session() as session:
            db = Database(session)
            channels = await db.get_sponsor_channels()
        
        if not channels:
            return await handler(event, data)

        # 3. Parallel Subscription Check
        async def check_one(ch):
            try:
                # 5s timeout per check to avoid infinite hangs
                async with asyncio.timeout(5):
                    member = await bot.get_chat_member(chat_id=ch.channel_id, user_id=user.id)
                    if member.status in ["left", "kicked"]:
                        return ch
                return None
            except (Exception, asyncio.TimeoutError) as e:
                logger.warning(f"SKIPPING SUB CHECK for {ch.channel_id} ({ch.title}): {e}")
                return None

        tasks = [check_one(ch) for ch in channels]
        results = await asyncio.gather(*tasks)
        not_joined = [r for r in results if r is not None]

        if not_joined:
            kb_list = []
            for ch in not_joined:
                # Priority: Username -> Invite Link -> Support link
                if ch.username:
                    url = f"https://t.me/{ch.username.replace('@', '')}"
                elif ch.invite_link:
                    url = ch.invite_link
                else:
                    url = f"https://t.me/Bekcode" # Default backup
                    
                kb_list.append([InlineKeyboardButton(text=f"A'zo bo'lish: {ch.title}", url=url)])
            
            kb_list.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
            kb = InlineKeyboardMarkup(inline_keyboard=kb_list)
            
            text = translator.get("sub_required", user.language)
            
            if isinstance(event, types.Message):
                await event.answer(text, reply_markup=kb)
            else:
                try:
                    await event.message.answer(text, reply_markup=kb)
                except Exception:
                    await event.message.edit_text(text, reply_markup=kb)
                await event.answer()
            return

        # 4. Save to Cache if all checks passed
        if redis:
            await redis.set(f"sub_checked:{user.id}", "1", ex=600) # cache for 10 mins

        return await handler(event, data)
