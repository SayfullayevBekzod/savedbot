from aiogram import Router, F, types
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from bot.services.downloader import downloader
from bot.utils.i18n import translator
from bot.database.models import User
import hashlib
import logging

logger = logging.getLogger(__name__)
router = Router()

@router.inline_query()
async def handle_inline_query(inline_query: InlineQuery, user: User):
    query = inline_query.query.strip()
    if not query:
        return

    # For safety and speed, we only search if query is 3+ chars
    if len(query) < 3:
        return

    try:
        # We can use yt-dlp to 'search' or just provide an example
        # But real-time search in inline might be slow.
        # Let's provide a 'Download' result for the specific URL if it looks like one.
        
        results = []
        
        if query.startswith("http"):
            # It's a URL. Show a 'Download' option
            item_id = hashlib.md5(query.encode()).hexdigest()
            results.append(
                InlineQueryResultArticle(
                    id=item_id,
                    title="📥 Videoni yuklab olish",
                    description=query,
                    input_message_content=InputTextMessageContent(
                        message_text=query
                    )
                )
            )
        else:
            # It's a search term.
            # In a real bot, you'd use a YouTube Search API or yt-dlp search:
            # results = await downloader.search(query)
            
            # To keep it snappy, let's suggest a search
            results.append(
                InlineQueryResultArticle(
                    id="search_prompt",
                    title=f"🔍 Qidirish: {query}",
                    description="YouTube'dan videolar qidirish (kelajakda)",
                    input_message_content=InputTextMessageContent(
                        message_text=f"Qidiruv natijasi: {query}"
                    )
                )
            )

        await inline_query.answer(results, cache_time=300)
        
    except Exception as e:
        logger.error(f"Inline query error: {e}")
