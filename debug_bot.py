import asyncio
import traceback
from bot.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("CRITICAL ERROR DURING BOT STARTUP:")
        traceback.print_exc()
