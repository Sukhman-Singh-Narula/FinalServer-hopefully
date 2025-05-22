# app/redis/redis_client.py
import redis.asyncio as redis
import os
import logging
import socket

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Global redis client instance
_redis_client = None

async def get_redis_client():
    """Get or create Redis client instance with fallback mechanisms"""
    global _redis_client
    
    if _redis_client is None:
        # Get Redis connection details from environment
        primary_host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", 6379))
        db = int(os.getenv("REDIS_DB", 0))
        
        # List of possible Redis hosts to try
        hosts_to_try = [
            primary_host,            # Try the configured host first
            "redis",                 # Then try the service name
            "finalserver-redis-1",   # Then try the container name
            "172.19.0.2",            # Then try a common Docker IP
            "127.0.0.1"              # Last resort: localhost
        ]
        
        # Remove duplicates while preserving order
        hosts_to_try = list(dict.fromkeys(hosts_to_try))
        
        logger.info(f"Attempting to connect to Redis using hosts: {hosts_to_try}")
        
        # Try each host until one works
        for host in hosts_to_try:
            try:
                logger.info(f"Trying to connect to Redis at {host}:{port}")
                
                # Try to resolve hostname first to avoid long timeouts
                if host != "127.0.0.1" and not host.startswith("172."):
                    try:
                        resolved_ip = socket.gethostbyname(host)
                        logger.info(f"Resolved {host} to {resolved_ip}")
                    except socket.gaierror:
                        logger.warning(f"Could not resolve hostname {host}, but trying anyway")
                
                # Create Redis client
                _redis_client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    decode_responses=False,
                    socket_timeout=3,       # Short timeout to fail fast
                    socket_connect_timeout=3
                )
                
                # Test connection
                await _redis_client.ping()
                logger.info(f"Successfully connected to Redis at {host}:{port}")
                break
                
            except redis.ConnectionError as e:
                logger.warning(f"Could not connect to Redis at {host}:{port}: {e}")
                _redis_client = None
                
            except Exception as e:
                logger.error(f"Unexpected error connecting to Redis at {host}:{port}: {e}")
                _redis_client = None
        
        if _redis_client is None:
            logger.error("Failed to connect to Redis after trying all hosts")
            raise Exception(f"Could not connect to Redis after trying: {', '.join(hosts_to_try)}")
    
    return _redis_client

async def get_redis_pubsub():
    """Get a new Redis PubSub instance"""
    client = await get_redis_client()
    return client.pubsub()