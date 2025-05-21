#!/bin/bash

echo "=== Starting Language Tutor Application ==="

# Start just the Redis container first
docker-compose up -d redis

# Wait for Redis to start
echo "Waiting for Redis to start..."
sleep 5

# Get the Redis container IP address
REDIS_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' finalserver-redis-1)
echo "Redis container IP address: $REDIS_IP"

# Test if Redis is reachable by IP
echo "Testing Redis connection using IP address..."
if docker run --rm --network finalserver_app-network redis:6-alpine redis-cli -h $REDIS_IP ping | grep -q "PONG"; then
    echo "Redis is working at IP $REDIS_IP"
else
    echo "Error: Redis connection failed! Exiting."
    exit 1
fi

# Create a temporary docker-compose file with the correct Redis IP
cp docker-compose.yml docker-compose.temp.yml
sed -i "s/REDIS_HOST=IP_PLACEHOLDER/REDIS_HOST=$REDIS_IP/g" docker-compose.temp.yml

# Start the rest of the containers using the temporary file
echo "Starting other containers with Redis IP: $REDIS_IP"
docker-compose -f docker-compose.temp.yml up -d app worker-manager audio-worker

# Clean up the temporary file
rm docker-compose.temp.yml

echo ""
echo "=== Language Tutor Application Started ==="
echo "Redis IP: $REDIS_IP"
echo "To view logs, run: docker-compose logs -f"
echo "To stop the application, run: docker-compose down"