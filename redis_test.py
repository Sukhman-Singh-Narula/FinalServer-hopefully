# redis_test.py
import redis
import os
import sys
import time

def test_redis_connection():
    # Get Redis connection details from environment or defaults
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_db = int(os.getenv("REDIS_DB", 0))
    
    print(f"Testing connection to Redis at {redis_host}:{redis_port}...")
    
    # Try to connect with retries
    max_retries = 5
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Create Redis client
            redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                socket_timeout=5
            )
            
            # Test connection with ping
            response = redis_client.ping()
            print(f"Connected to Redis! Response: {response}")
            
            # Try a simple set and get operation
            redis_client.set("test_key", "Hello from test script")
            value = redis_client.get("test_key")
            print(f"Set and retrieved value: {value}")
            
            return True
            
        except redis.exceptions.ConnectionError as e:
            print(f"Connection attempt {attempt+1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Max retries exceeded. Could not connect to Redis.")
                return False
        
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False

if __name__ == "__main__":
    success = test_redis_connection()
    sys.exit(0 if success else 1)