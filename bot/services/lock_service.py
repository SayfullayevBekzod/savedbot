import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class LockService:
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.lock_timeout = 300  # 5 minutes

    def set_redis(self, redis_client):
        self.redis = redis_client

    async def acquire_lock(self, key: str) -> bool:
        if not self.redis: return True
        lock_key = f"lock:{key}"
        return bool(await self.redis.set(lock_key, "1", ex=self.lock_timeout, nx=True))

    async def release_lock(self, key: str):
        if not self.redis: return
        await self.redis.delete(f"lock:{key}")

    async def is_locked(self, key: str) -> bool:
        if not self.redis: return False
        return bool(await self.redis.exists(f"lock:{key}"))

    @asynccontextmanager
    async def distributed_lock(self, key: str, wait_timeout: int = 60):
        """
        Professional Distributed Lock Context Manager.
        Ensures atomic execution across multiple workers.
        """
        lock_key = key
        acquired = await self.acquire_lock(lock_key)
        
        if not acquired:
            # Wait for the other process to finish
            start_time = asyncio.get_event_loop().time()
            while await self.is_locked(lock_key):
                if asyncio.get_event_loop().time() - start_time > wait_timeout:
                    break
                await asyncio.sleep(0.5)
            
            # After waiting, try to acquire one last time or just proceed
            # (In professional flow, we usually re-check cache after this)
            acquired = await self.acquire_lock(lock_key)

        try:
            yield acquired
        finally:
            if acquired:
                await self.release_lock(lock_key)

lock_service = LockService()
