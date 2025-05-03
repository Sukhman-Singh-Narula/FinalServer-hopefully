# app/redis_client.py
import redis.asyncio as redis
from app.config import REDIS_HOST, REDIS_PORT, REDIS_DB

# Global redis client instance
_redis_client = None

async def get_redis_client():
    """Get or create Redis client instance"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=False
        )
        
        # Test connection
        try:
            await _redis_client.ping()
        except redis.ConnectionError:
            # Handle connection error
            raise Exception(f"Could not connect to Redis at {REDIS_HOST}:{REDIS_PORT}")
            
    return _redis_client

async def get_redis_pubsub():
    """Get a new Redis PubSub instance"""
    client = await get_redis_client()
    return client.pubsub()