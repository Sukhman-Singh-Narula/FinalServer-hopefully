#!/bin/bash

echo "=== Starting Redis Test With IP Address ==="

# Start just the Redis container
docker-compose -f test-redis.yml up -d redis

# Wait a few seconds for Redis to start
echo "Waiting for Redis to start..."
sleep 5

# Get the Redis container IP address
REDIS_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' finalserver-redis-1)
echo "Redis container IP address: $REDIS_IP"

# Test Redis connection using IP address
echo "Testing Redis connection using IP address..."
docker run --rm redis:6-alpine redis-cli -h $REDIS_IP ping

# Clean up
docker-compose -f test-redis.yml down

echo "=== Redis IP test complete ==="