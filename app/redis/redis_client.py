import redis.asyncio as async_redis
import redis as sync_redis
import os
import logging
import socket

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Global redis client instances
_async_redis_client = None
_sync_redis_client = None

def get_connection_params():
    """Get Redis connection parameters with fallback hosts"""
    primary_host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", 6379))
    db = int(os.getenv("REDIS_DB", 0))
    
    hosts_to_try = [
        primary_host,            # Try the configured host first
        "redis",                 # Then try the service name
        "finalserver-redis-1",   # Then try the container name
        "172.19.0.2",            # Then try a common Docker IP
        "127.0.0.1"              # Last resort: localhost
    ]
    
    # Remove duplicates while preserving order
    hosts_to_try = list(dict.fromkeys(hosts_to_try))
    
    return hosts_to_try, port, db

def get_sync_redis_client():
    """Get or create synchronous Redis client instance with fallback mechanisms"""
    global _sync_redis_client
    
    if _sync_redis_client is None:
        hosts_to_try, port, db = get_connection_params()
        
        logger.info(f"Attempting to connect to Redis (sync) using hosts: {hosts_to_try}")
        
        # Try each host until one works
        for host in hosts_to_try:
            try:
                logger.info(f"Trying to connect to Redis (sync) at {host}:{port}")
                
                # Create Redis client
                _sync_redis_client = sync_redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    decode_responses=False,
                    socket_timeout=3,
                    socket_connect_timeout=3
                )
                
                # Test connection
                _sync_redis_client.ping()
                logger.info(f"Successfully connected to Redis (sync) at {host}:{port}")
                break
                
            except sync_redis.ConnectionError as e:
                logger.warning(f"Could not connect to Redis (sync) at {host}:{port}: {e}")
                _sync_redis_client = None
                
            except Exception as e:
                logger.error(f"Unexpected error connecting to Redis (sync) at {host}:{port}: {e}")
                _sync_redis_client = None
        
        if _sync_redis_client is None:
            logger.error("Failed to connect to Redis (sync) after trying all hosts")
            raise Exception(f"Could not connect to Redis after trying: {', '.join(hosts_to_try)}")
    
    return _sync_redis_client

async def get_redis_client():
    """Get or create async Redis client instance with fallback mechanisms"""
    global _async_redis_client
    
    if _async_redis_client is None:
        hosts_to_try, port, db = get_connection_params()
        
        logger.info(f"Attempting to connect to Redis (async) using hosts: {hosts_to_try}")
        
        # Try each host until one works
        for host in hosts_to_try:
            try:
                logger.info(f"Trying to connect to Redis (async) at {host}:{port}")
                
                # Try to resolve hostname first to avoid long timeouts
                if host != "127.0.0.1" and not host.startswith("172."):
                    try:
                        resolved_ip = socket.gethostbyname(host)
                        logger.info(f"Resolved {host} to {resolved_ip}")
                    except socket.gaierror:
                        logger.warning(f"Could not resolve hostname {host}, but trying anyway")
                
                # Create Redis client
                _async_redis_client = async_redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    decode_responses=False,
                    socket_timeout=3,
                    socket_connect_timeout=3
                )
                
                # Test connection
                await _async_redis_client.ping()
                logger.info(f"Successfully connected to Redis (async) at {host}:{port}")
                break
                
            except async_redis.ConnectionError as e:
                logger.warning(f"Could not connect to Redis (async) at {host}:{port}: {e}")
                _async_redis_client = None
                
            except Exception as e:
                logger.error(f"Unexpected error connecting to Redis (async) at {host}:{port}: {e}")
                _async_redis_client = None
        
        if _async_redis_client is None:
            logger.error("Failed to connect to Redis (async) after trying all hosts")
            raise Exception(f"Could not connect to Redis after trying: {', '.join(hosts_to_try)}")
    
    return _async_redis_client

async def get_redis_pubsub():
    """Get a new Redis PubSub instance"""
    client = await get_redis_client()
    return client.pubsub()