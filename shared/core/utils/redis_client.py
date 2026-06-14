"""
MuleShield AI - Redis Client
Redis connection pool for caching and idempotency
"""

import os
import redis.asyncio as redis
from typing import Optional

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_redis_pool: Optional[redis.ConnectionPool] = None


async def get_redis_pool() -> redis.ConnectionPool:
    """Get or create Redis connection pool"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(
            REDIS_URL,
            max_connections=50,
            decode_responses=True,
        )
    return _redis_pool


async def get_redis_client() -> redis.Redis:
    """Get Redis client from pool"""
    pool = await get_redis_pool()
    return redis.Redis(connection_pool=pool)


async def close_redis_pool():
    """Close Redis connection pool"""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
