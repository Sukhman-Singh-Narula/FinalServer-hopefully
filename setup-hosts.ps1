# PowerShell script to set up Docker hosts for Redis

Write-Host "=== Setting up Redis host entry for containers ===" -ForegroundColor Cyan

# Get the Redis container IP address
$REDIS_IP = docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' finalserver-redis-1
Write-Host "Redis container IP address: $REDIS_IP" -ForegroundColor Green

if ($REDIS_IP -eq "") {
    Write-Host "Error: Could not find Redis IP address!" -ForegroundColor Red
    exit 1
}

# Add hosts entry to each container
Write-Host "Adding hosts entry to containers..." -ForegroundColor Yellow

docker exec finalserver-app-1 bash -c "echo '$REDIS_IP redis' >> /etc/hosts"
docker exec finalserver-worker-manager-1 bash -c "echo '$REDIS_IP redis' >> /etc/hosts"
docker exec finalserver-audio-worker-1 bash -c "echo '$REDIS_IP redis' >> /etc/hosts"

Write-Host "Testing Redis connection from containers..." -ForegroundColor Yellow

# Test that the hosts entry works
$app_test = docker exec finalserver-app-1 bash -c "apt-get update -q >/dev/null && apt-get install -y redis-tools >/dev/null && redis-cli -h redis ping"
if ($app_test -eq "PONG") {
    Write-Host "App container can connect to Redis ✓" -ForegroundColor Green
} else {
    Write-Host "App container CANNOT connect to Redis ✗" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Setup completed! ===" -ForegroundColor Green