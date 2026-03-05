import asyncio
import logging
from arq import cron
from bot.config import config
from bot.services.downloader import downloader
from bot.services.caching import cache_service
from aiogram import Bot

async def download_task(ctx, url: str, user_id: int, message_id: int):
    """
    Background task to handle heavy downloads.
    """
    try:
        # Step 1: Download
        result = await downloader.download(url, max_size_mb=config.MAX_VIDEO_SIZE_MB)
        
        if result and "file_path" in result:
            # Step 2: Send to user (handled by the caller or here)
            # For now, let's assume we notify the bot handler via some mechanism or just send here
            # But usually, it's better to keep the worker focused on IO/CPU
            return result
        return {"error": "Download failed"}
        
    except Exception as e:
        logging.error(f"Worker task error: {e}")
        return {"error": str(e)}

async def broadcast_task(ctx, from_chat_id: int, message_id: int, user_ids: list[int]):
    """
    Background task to broadcast a message to many users with flood protection.
    """
    from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest
    bot: Bot = ctx['bot']
    success = 0
    failed = 0
    blocked = 0
    
    logging.info(f"Starting broadcast for {len(user_ids)} users...")
    
    for uid in user_ids:
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            success += 1
            await asyncio.sleep(0.05) # ~20 msgs/s
        except TelegramRetryAfter as e:
            logging.warning(f"Flood limit reached. Sleeping for {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            # Retry after sleep
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=message_id)
                success += 1
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            blocked += 1
        except TelegramBadRequest as e:
            logging.error(f"Bad request for user {uid}: {e}")
            failed += 1
        except Exception as e:
            logging.error(f"Unexpected broadcast error for {uid}: {e}")
            failed += 1
            await asyncio.sleep(0.05)
            
    logging.info(f"Broadcast finished. Success: {success}, Blocked: {blocked}, Failed: {failed}")
    return {"success": success, "failed": failed, "blocked": blocked}

async def startup(ctx):
    ctx['bot'] = Bot(token=config.BOT_TOKEN)
    logging.info("Worker started")

async def shutdown(ctx):
    if 'bot' in ctx:
        await ctx['bot'].session.close()
    logging.info("Worker shut down")

from arq.connections import RedisSettings

class WorkerSettings:
    functions = [download_task, broadcast_task]
    redis_settings = RedisSettings.from_dsn(config.ARQ_REDIS_URL)
    job_timeout = 600
    max_jobs = 20
    on_startup = startup
    on_shutdown = shutdown
    # Clear downloads older than 24h
    cron_jobs = [
        cron(downloader.cleanup_old_files, hour=3, minute=0),
        cron(cache_service.cleanup_expired_cache, hour=4, minute=0)
    ]
