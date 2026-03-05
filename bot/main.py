import asyncio
import logging
import os
import re
import socket
import sys
from urllib.parse import quote, urlsplit, urlunsplit
import redis.asyncio as redis
from arq.connections import create_pool, RedisSettings
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import config, normalize_redis_url, normalize_webhook_host
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


def _mask_redis_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        netloc = parsed.netloc
        if "@" in netloc:
            creds, host = netloc.rsplit("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                netloc = f"{user}:***@{host}"
            else:
                netloc = f"***@{host}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "<invalid-url>"


def _replace_redis_db(url: str, db_index: int) -> str:
    try:
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, f"/{db_index}", parsed.query, parsed.fragment))
    except Exception:
        return url


def _build_upstash_redis_url(rest_url: str, token: str, db_index: int = 0):
    if not isinstance(rest_url, str) or not isinstance(token, str):
        return None

    cleaned_rest = rest_url.strip().strip("\"'")
    cleaned_token = token.strip().strip("\"'")
    if not cleaned_rest or not cleaned_token:
        return None

    parsed = urlsplit(cleaned_rest if "://" in cleaned_rest else f"https://{cleaned_rest}")
    host = parsed.hostname
    if not host:
        return None

    port = parsed.port or 6379
    encoded_token = quote(cleaned_token, safe="")
    return f"rediss://default:{encoded_token}@{host}:{port}/{db_index}"


def _repair_missing_at_in_redis_url(url: str):
    if not isinstance(url, str):
        return None
    token = (config.UPSTASH_REDIS_REST_TOKEN or "").strip().strip("\"'")
    if not token:
        return None

    # Handles malformed values like: redis://default:host:6379 or rediss://default:host:6379/0
    match = re.match(
        r"^(?:redis|rediss)://default:(?P<host>[^:/@]+):(?P<port>\d+)(?P<path>/\d+)?$",
        url.strip(),
    )
    if not match:
        return None

    host = match.group("host")
    port = match.group("port")
    path = match.group("path") or "/0"
    encoded_token = quote(token, safe="")
    return f"rediss://default:{encoded_token}@{host}:{port}{path}"


async def _create_redis_client():
    candidates = []
    primary = normalize_redis_url(config.REDIS_URL)
    if isinstance(primary, str) and primary:
        candidates.append(("REDIS_URL", primary))
        repaired_primary = _repair_missing_at_in_redis_url(primary)
        if repaired_primary and all(url != repaired_primary for _, url in candidates):
            candidates.append(("REDIS_URL(repaired)", repaired_primary))

    upstash_candidate = _build_upstash_redis_url(
        config.UPSTASH_REDIS_REST_URL,
        config.UPSTASH_REDIS_REST_TOKEN,
        db_index=0,
    )
    if upstash_candidate and all(url != upstash_candidate for _, url in candidates):
        candidates.append(("UPSTASH_REDIS_REST_URL/TOKEN", upstash_candidate))

    errors = []
    for source, candidate in candidates:
        client = None
        try:
            client = redis.from_url(candidate, decode_responses=True)
            await client.ping()
            logger.info(f"Connected to Redis via {source}.")
            if source != "REDIS_URL":
                logger.warning(f"Redis URL fallback used: {_mask_redis_url(candidate)}")
            return client, candidate
        except Exception as e:
            errors.append(f"{source} ({_mask_redis_url(candidate)}): {e}")
            if client:
                try:
                    await client.aclose()
                except Exception:
                    pass

    if errors:
        logger.warning("Redis unavailable; running with reduced functionality.")
        for item in errors:
            logger.warning(f"Redis candidate failed: {item}")
    else:
        logger.warning("Redis unavailable; no candidate Redis URL found.")
    return None, None


async def _create_arq_pool(primary_redis_url: str = None):
    candidates = []
    arq_url = normalize_redis_url(config.ARQ_REDIS_URL)
    if isinstance(arq_url, str) and arq_url:
        candidates.append(("ARQ_REDIS_URL", arq_url))
        repaired_arq = _repair_missing_at_in_redis_url(arq_url)
        if repaired_arq and all(url != repaired_arq for _, url in candidates):
            candidates.append(("ARQ_REDIS_URL(repaired)", repaired_arq))

    if isinstance(primary_redis_url, str) and primary_redis_url:
        derived = _replace_redis_db(primary_redis_url, 1)
        if all(url != derived for _, url in candidates):
            candidates.append(("REDIS_URL(db=1)", derived))

    upstash_candidate = _build_upstash_redis_url(
        config.UPSTASH_REDIS_REST_URL,
        config.UPSTASH_REDIS_REST_TOKEN,
        db_index=1,
    )
    if upstash_candidate and all(url != upstash_candidate for _, url in candidates):
        candidates.append(("UPSTASH_REDIS_REST_URL/TOKEN(db=1)", upstash_candidate))

    for source, candidate in candidates:
        try:
            pool = await create_pool(RedisSettings.from_dsn(candidate))
            logger.info(f"Connected to ARQ Redis via {source}.")
            return pool
        except Exception as e:
            logger.warning(f"ARQ Redis candidate failed ({source}): {e}")

    logger.warning("ARQ Redis unavailable; background queue disabled.")
    return None


async def _start_health_server(port: int):
    app = web.Application()
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    return runner


async def _get_bot_identity_with_retry(bot: Bot):
    while True:
        try:
            return await bot.get_me()
        except TelegramUnauthorizedError:
            logger.error(
                "BOT_TOKEN is invalid (Telegram Unauthorized). "
                "Update BOT_TOKEN in Render environment and redeploy. Retrying in 60 seconds..."
            )
            await asyncio.sleep(60)
        except Exception as e:
            logger.warning(f"Failed to get bot identity: {e}. Retrying in 10 seconds...")
            await asyncio.sleep(10)

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

async def on_startup(bot: Bot, webhook_host: str = None):
    """Actions to perform on startup (Webhook only)."""
    effective_host = normalize_webhook_host(webhook_host or config.WEBHOOK_HOST)
    if effective_host:
        webhook_url = f"{effective_host}{config.WEBHOOK_PATH}"
        logger.info(f"Setting webhook: {webhook_url}")
        await bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "inline_query"]
        )

async def on_shutdown(bot: Bot, redis_client=None, arq_redis=None, webhook_host: str = None):
    """Actions to perform on shutdown."""
    effective_host = normalize_webhook_host(webhook_host or config.WEBHOOK_HOST)
    if effective_host:
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
    startup_health_runner = None

    # 1. Initialize DB
    logger.info("Initializing database...")
    await init_db()

    render_port = os.getenv("PORT")
    if render_port and os.getenv("INTERNAL_HEALTH_SERVER_ACTIVE") != "1":
        startup_health_runner = await _start_health_server(int(render_port))
        logger.info(f"Startup health server opened on port {render_port}.")

    # 2. Initialize Redis
    logger.info("Connecting to Redis...")
    redis_client, active_redis_url = await _create_redis_client()
    
    # 2.1 Initialize ARQ Redis pool for admin broadcast/background jobs
    arq_redis = await _create_arq_pool(active_redis_url)

    # 2.2 Inject Redis into global services (CRITICAL for caching)
    from bot.services.caching import cache_service
    from bot.services.lock_service import lock_service
    from bot.services.recognition_service import recognition_service
    cache_service.set_redis(redis_client)
    lock_service.set_redis(redis_client)
    recognition_service.set_redis(redis_client)
    if redis_client:
        logger.info("Redis injected into CacheService, LockService, and RecognitionService.")
    else:
        logger.warning("Running without Redis. Locking/cache/rate-limit features are reduced.")

    # 3. Initialize bot and dispatcher
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    dp = Dispatcher()
    dp["redis_client"] = redis_client
    dp["arq_redis"] = arq_redis

    # Cache Bot Identity
    bot_info = await _get_bot_identity_with_retry(bot)
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

    webhook_host = normalize_webhook_host(config.WEBHOOK_HOST)

    # 6. Mode Selection: Webhook or Polling
    if webhook_host and str(webhook_host).startswith("http"):
        # PRODUCTION: Webhook Mode
        if startup_health_runner:
            await startup_health_runner.cleanup()
            startup_health_runner = None

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
        app.on_startup.append(lambda _: on_startup(bot, webhook_host))
        app.on_shutdown.append(lambda _: on_shutdown(bot, redis_client, arq_redis, webhook_host))

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
        health_runner = startup_health_runner
        startup_health_runner = None
        render_port = os.getenv("PORT")
        if render_port and not health_runner and os.getenv("INTERNAL_HEALTH_SERVER_ACTIVE") != "1":
            health_runner = await _start_health_server(int(render_port))
            logger.warning(
                f"PORT={render_port} detected but WEBHOOK_HOST not configured. "
                "Running polling with health server fallback."
            )
        # Ensure webhook is deleted before polling to avoid conflict
        await bot.delete_webhook(drop_pending_updates=True)

        polling_lock = None
        if redis_client:
            while polling_lock is None:
                try:
                    polling_lock = await acquire_polling_lock(redis_client, bot_info.id, ttl_seconds=30)
                    logger.info("Polling lock acquired.")
                except RuntimeError as e:
                    logger.warning(f"{e}. Waiting 10 seconds before retrying lock acquisition...")
                    await asyncio.sleep(10)

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
            if health_runner:
                await health_runner.cleanup()
            await on_shutdown(bot, redis_client, arq_redis, webhook_host)

    if startup_health_runner:
        await startup_health_runner.cleanup()

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
