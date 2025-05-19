# Script to modify app/config.py for Docker compatibility
# This ensures Redis connections use the correct host name in Docker

import os
import re

# Config file path
config_file = 'app/config.py'

def update_config():
    """Update the config.py file to work with Docker"""
    print("Updating config.py for Docker compatibility...")
    
    # Check if the file exists
    if not os.path.exists(config_file):
        print(f"Error: {config_file} not found!")
        return False
    
    # Read the file
    with open(config_file, 'r') as f:
        content = f.read()
    
    # Update Redis host configuration
    new_content = re.sub(
        r'REDIS_HOST\s*=\s*os.getenv\(["\']REDIS_HOST["\'],\s*["\']localhost["\']\)',
        'REDIS_HOST = os.getenv("REDIS_HOST", "redis")',
        content
    )
    
    # Also update any Redis connection instances
    new_content = re.sub(
        r'redis.Redis\(host=\'localhost\'',
        'redis.Redis(host=os.getenv("REDIS_HOST", "redis")',
        new_content
    )
    
    # Check if content changed
    if new_content != content:
        # Write the file back
        with open(config_file, 'w') as f:
            f.write(new_content)
        print(f"Updated {config_file} - Redis host configuration now uses environment variable")
        return True
    else:
        print(f"No changes needed in {config_file}")
        return False

if __name__ == "__main__":
    update_config()