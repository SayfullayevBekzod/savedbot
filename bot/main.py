import asyncio
import logging
import os
import socket
import sys
import redis.asyncio as redis
from arq.connections import create_pool, RedisSettings
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import config
from bot.handlers.base import router as base_router
from bot.handlers.recognition import router as recognition_router
from bot.handlers.inline import router as inline_router
from bot.admin.handlers import router as admin_router
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.ratelimit import RateLimitMiddleware
from bot.middlewares.logging import LoggingMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.database.session import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

LOCK_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], tonumber(ARGV[2]))
else
    return 0
end
"""

LOCK_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def _normalize_redis_url(url: str) -> str:
    if not isinstance(url, str):
        return url
    value = url.strip().strip("\"'")
    replacements = {
        "redis://https://": "rediss://",
        "rediss://https://": "rediss://",
        "redis://http://": "redis://",
        "rediss://http://": "redis://",
        "redis://https:": "rediss://",
        "rediss://https:": "rediss://",
        "redis://http:": "redis://",
        "rediss://http:": "redis://",
        "https://": "rediss://",
        "http://": "redis://",
    }
    for bad_prefix, good_prefix in replacements.items():
        if value.startswith(bad_prefix):
            return good_prefix + value[len(bad_prefix):]
    return value

async def acquire_polling_lock(redis_client, bot_id: int, ttl_seconds: int = 90):
    """
    Ensure only one polling instance is active per bot token.
    Prevents TelegramConflictError from parallel getUpdates workers.
    """
    lock_key = f"bot:polling_lock:{bot_id}"
    lock_value = f"{socket.gethostname()}:{os.getpid()}"
    acquired = await redis_client.set(lock_key, lock_value, ex=ttl_seconds, nx=True)
    if not acquired:
        holder = await redis_client.get(lock_key)
        raise RuntimeError(f"Polling lock already held by {holder or 'unknown instance'}")

    stop_event = asyncio.Event()

    async def renew_lock():
        while not stop_event.is_set():
            await asyncio.sleep(max(10, ttl_seconds // 3))
            try:
                renewed = await redis_client.eval(
                    LOCK_RENEW_SCRIPT, 1, lock_key, lock_value, str(ttl_seconds)
                )
                if renewed != 1:
                    logger.warning("Polling lock renewal failed; instance may lose lock.")
            except Exception as e:
                logger.warning(f"Polling lock renewal error: {e}")

    renew_task = asyncio.create_task(renew_lock())
    return lock_key, lock_value, stop_event, renew_task

async def release_polling_lock(redis_client, lock_key: str, lock_value: str, stop_event: asyncio.Event, renew_task: asyncio.Task):
    stop_event.set()
    renew_task.cancel()
    try:
        await renew_task
    except asyncio.CancelledError:
        pass
    try:
        await redis_client.eval(LOCK_RELEASE_SCRIPT, 1, lock_key, lock_value)
    except Exception as e:
        logger.warning(f"Failed to release polling lock: {e}")

async def on_startup(bot: Bot):
    """Actions to perform on startup (Webhook only)."""
    if config.WEBHOOK_HOST:
        webhook_url = f"{config.WEBHOOK_HOST}{config.WEBHOOK_PATH}"
        logger.info(f"Setting webhook: {webhook_url}")
        await bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "inline_query"]
        )

async def on_shutdown(bot: Bot, redis_client=None, arq_redis=None):
    """Actions to perform on shutdown."""
    if config.WEBHOOK_HOST:
        logger.info("Deleting webhook...")
        await bot.delete_webhook()

    if arq_redis:
        await arq_redis.aclose()
        logger.info("ARQ Redis connection closed.")

    if redis_client:
        await redis_client.aclose()
        logger.info("Redis connection closed.")

    await bot.session.close()
    logger.info("Bot session closed.")

async def health_check(request):
    """Health check endpoint for production monitoring."""
    return web.Response(text="OK", status=200)

async def serve_profile(request):
    """Serve the TWA Profile HTML."""
    try:
        with open("bot/static/profile.html", "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type='text/html')
    except Exception:
        return web.Response(text="Profile template not found.", status=404)

async def api_user_profile(request):
    """API for TWA to get user specific data."""
    user_id = request.query.get("id")
    if not user_id or not user_id.isdigit():
        return web.json_response({"error": "Invalid ID"}, status=400)
    
    user_id = int(user_id)
    from bot.database.session import async_session, Database
    async with async_session() as session:
        db = Database(session)
        user = await db.get_user(user_id)
        if not user:
            return web.json_response({"error": "User not found"}, status=404)
        
        dl_count = await db.get_user_download_count(user_id)
        return web.json_response({
            "id": user.id,
            "downloads": dl_count,
            "referrals": user.referral_count
        })

async def main():
    # 1. Initialize DB
    logger.info("Initializing database...")
    await init_db()

    # 2. Initialize Redis
    logger.info("Connecting to Redis...")
    redis_url = _normalize_redis_url(config.REDIS_URL)
    if redis_url != config.REDIS_URL:
        logger.warning("REDIS_URL was normalized from malformed input.")
    try:
        redis_client = redis.from_url(redis_url, decode_responses=True)
    except ValueError as e:
        raise RuntimeError(
            "Invalid REDIS_URL format. Use redis://host:port/db "
            "or rediss://default:PASSWORD@host:port/db"
        ) from e
    
    # 2.1 Initialize ARQ Redis pool for admin broadcast/background jobs
    arq_redis = None
    arq_redis_url = _normalize_redis_url(config.ARQ_REDIS_URL)
    try:
        arq_redis = await create_pool(RedisSettings.from_dsn(arq_redis_url))
        logger.info("Connected to ARQ Redis.")
    except Exception as e:
        logger.warning(f"ARQ Redis unavailable: {e}")

    # 2.2 Inject Redis into global services (CRITICAL for caching)
    from bot.services.caching import cache_service
    from bot.services.lock_service import lock_service
    from bot.services.recognition_service import recognition_service
    cache_service.set_redis(redis_client)
    lock_service.set_redis(redis_client)
    recognition_service.set_redis(redis_client)
    logger.info("Redis injected into CacheService, LockService, and RecognitionService.")

    # 3. Initialize bot and dispatcher
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    dp = Dispatcher()
    dp["redis_client"] = redis_client
    dp["arq_redis"] = arq_redis

    # Cache Bot Identity
    bot_info = await bot.get_me()
    logger.info(f"Bot initialized: @{bot_info.username}")

    # 4. Register Middlewares
    dp.update.outer_middleware(LoggingMiddleware())
    dp.message.middleware(RateLimitMiddleware(redis_client))
    dp.callback_query.middleware(RateLimitMiddleware(redis_client))
    dp.message.middleware(AuthMiddleware(redis_client))
    dp.callback_query.middleware(AuthMiddleware(redis_client))
    dp.inline_query.middleware(AuthMiddleware(redis_client))
    
    # Subscription Check (After Auth)
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())
    dp.inline_query.middleware(SubscriptionMiddleware())

    # 5. Register Routers
    dp.include_router(admin_router)
    dp.include_router(inline_router)
    dp.include_router(recognition_router)
    dp.include_router(base_router)

    # 6. Mode Selection: Webhook or Polling
    if config.WEBHOOK_HOST and config.WEBHOOK_HOST.startswith("http"):
        # PRODUCTION: Webhook Mode
        app = web.Application()
        
        # Healthcheck endpoint
        app.router.add_get("/health", health_check)
        
        # TWA Routes
        app.router.add_get("/profile", serve_profile)
        app.router.add_get("/api/user/profile", api_user_profile)

        # Webhook Handler
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        )
        # Register the webhook handler on the specified path
        webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)

        # Setup application with startup and shutdown hooks
        setup_application(app, dp, bot=bot, redis_client=redis_client, arq_redis=arq_redis)
        
        # Add custom lifecycle hooks
        app.on_startup.append(lambda _: on_startup(bot))
        app.on_shutdown.append(lambda _: on_shutdown(bot, redis_client, arq_redis))

        port = int(os.getenv("PORT", str(config.BACKEND_PORT)))
        logger.info(f"Starting Webhook server on port {port}...")
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host="0.0.0.0", port=port)
        await site.start()

        # Keep running
        await asyncio.Event().wait()
    else:
        # DEVELOPMENT: Polling Mode
        logger.info("Starting Polling mode (Dev)...")
        # Ensure webhook is deleted before polling to avoid conflict
        await bot.delete_webhook(drop_pending_updates=True)

        polling_lock = None
        if redis_client:
            try:
                polling_lock = await acquire_polling_lock(redis_client, bot_info.id, ttl_seconds=30)
                logger.info("Polling lock acquired.")
            except RuntimeError as e:
                logger.error(f"{e}. Refusing to start second polling instance.")
                await on_shutdown(bot, redis_client, arq_redis)
                return

        try:
            while True:
                try:
                    await dp.start_polling(bot, redis_client=redis_client, arq_redis=arq_redis)
                    break # Normal exit
                except Exception as e:
                    logger.error(f"Polling crashed with error: {e}. Restarting in 5 seconds...")
                    await asyncio.sleep(5)
        finally:
            if polling_lock:
                await release_polling_lock(redis_client, *polling_lock)
            await on_shutdown(bot, redis_client, arq_redis)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot execution stopped.")
    except Exception:
        logger.exception("Fatal startup/runtime error.")
        if sys.stdin and sys.stdin.isatty():
            try:
                input("Xatolik yuz berdi. Yopish uchun Enter bosing...")
            except EOFError:
                pass
