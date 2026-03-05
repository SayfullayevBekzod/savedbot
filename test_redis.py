import asyncio
import redis.asyncio as redis

async def test_redis():
    urls = [
        "redis://localhost:6379/0",
        "redis://localhost:6379/1"
    ]
    for url in urls:
        print(f"Testing {url}...")
        try:
            r = redis.from_url(url)
            ping = await r.ping()
            print(f"  Ping: {ping}")
            await r.set("test", "val")
            val = await r.get("test")
            print(f"  Set/Get: {val}")
            await r.aclose()
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_redis())
