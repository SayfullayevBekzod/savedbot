import asyncio
import redis.asyncio as redis
from bot.config import config

async def clear_lock():
    print(f"Connecting to Redis at {config.REDIS_URL}...")
    redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
    
    # Based on logs: bot id=8695254851
    bot_id = "8695254851"
    lock_key = f"bot:polling_lock:{bot_id}"
    
    deleted = await redis_client.delete(lock_key)
    if deleted:
        print(f"Successfully deleted stale lock key: {lock_key}")
    else:
        print(f"Lock key {lock_key} not found or already cleared.")
    
    # Also check if there's any other polling locks
    keys = await redis_client.keys("bot:polling_lock:*")
    if keys:
        print(f"Found other polling locks: {keys}. Clearing them too...")
        for k in keys:
            await redis_client.delete(k)
            print(f"Deleted {k}")

    await redis_client.aclose()

if __name__ == "__main__":
    asyncio.run(clear_lock())
