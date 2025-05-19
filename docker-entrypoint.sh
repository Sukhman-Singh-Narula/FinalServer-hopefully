#!/bin/bash
set -e

# Print welcome message
echo "Spanish Tutor Docker Container Starting..."

# Update Redis host if needed (for Docker)
if grep -q "localhost" app/config.py; then
  echo "Updating Redis configuration..."
  # Replace localhost with redis service name
  sed -i 's/REDIS_HOST = os.getenv("REDIS_HOST", "localhost")/REDIS_HOST = os.getenv("REDIS_HOST", "redis")/g' app/config.py
  echo "Updated Redis host in config.py"
fi

# Check if OpenAI API key is set
if [ -z "$OPENAI_API_KEY" ]; then
  echo "WARNING: OPENAI_API_KEY environment variable is not set!"
  echo "The application may not function correctly without it."
fi

# Execute the command passed to docker
echo "Running command: $@"
exec "$@"