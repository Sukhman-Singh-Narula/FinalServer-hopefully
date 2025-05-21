#!/bin/bash
set -e

# Wait for Redis to be ready
echo "Waiting for Redis..."
until redis-cli -h redis ping; do
  sleep 1
done
echo "Redis is ready!"

# Execute the passed command
exec "$@"