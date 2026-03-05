import asyncio
import logging
import os
from aiohttp import web

RESTART_DELAY_SECONDS = 10


async def _liveness_handler(_request):
    return web.Response(text="OK", status=200)


async def _start_liveness_server_if_needed():
    port = os.getenv("PORT")
    webhook_host = (os.getenv("WEBHOOK_HOST") or "").strip()

    # Render web service needs an open port. When WEBHOOK_HOST is not configured,
    # keep a minimal health server alive while polling/startup recovery is running.
    if not port or webhook_host:
        return None

    app = web.Application()
    app.router.add_get("/health", _liveness_handler)
    app.router.add_get("/", _liveness_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(port))
    await site.start()
    os.environ["INTERNAL_HEALTH_SERVER_ACTIVE"] = "1"
    logging.info(f"Liveness fallback server started on port {port}.")
    return runner


async def _run_supervisor():
    liveness_runner = await _start_liveness_server_if_needed()

    try:
        while True:
            try:
                from bot.main import main as bot_main
                await bot_main()
                logging.warning(
                    f"Bot main returned unexpectedly. Restarting in {RESTART_DELAY_SECONDS} seconds..."
                )
            except (KeyboardInterrupt, SystemExit):
                logging.info("Bot execution stopped.")
                return
            except Exception:
                logging.exception(
                    f"Fatal startup/runtime error. Restarting in {RESTART_DELAY_SECONDS} seconds..."
                )

            await asyncio.sleep(RESTART_DELAY_SECONDS)
    finally:
        if liveness_runner:
            await liveness_runner.cleanup()
            os.environ.pop("INTERNAL_HEALTH_SERVER_ACTIVE", None)


if __name__ == "__main__":
    try:
        asyncio.run(_run_supervisor())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot execution stopped.")
