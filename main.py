import asyncio
import logging
import sys

from bot.main import main


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot execution stopped.")
    except Exception:
        logging.exception("Fatal startup/runtime error.")
        if sys.stdin and sys.stdin.isatty():
            try:
                input("Xatolik yuz berdi. Yopish uchun Enter bosing...")
            except EOFError:
                pass
