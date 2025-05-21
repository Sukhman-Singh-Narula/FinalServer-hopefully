# PowerShell script to start the application using Redis IP address

Write-Host "=== Starting Language Tutor Application ===" -ForegroundColor Cyan

# Start just the Redis container first
docker-compose up -d redis

# Wait for Redis to start
Write-Host "Waiting for Redis to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Get the Redis container IP address
$REDIS_IP = docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' finalserver-redis-1
Write-Host "Redis container IP address: $REDIS_IP" -ForegroundColor Green

# Test if Redis is reachable by IP
Write-Host "Testing Redis connection using IP address..." -ForegroundColor Yellow
$testResult = docker run --rm --network finalserver_app-network redis:6-alpine redis-cli -h $REDIS_IP ping
if ($testResult -eq "PONG") {
    Write-Host "Redis is working at IP $REDIS_IP" -ForegroundColor Green
} else {
    Write-Host "Error: Redis connection failed! Exiting." -ForegroundColor Red
    exit 1
}

# Create a temporary docker-compose file with the correct Redis IP
Get-Content docker-compose.yml | ForEach-Object {
    $_ -replace 'REDIS_HOST=IP_PLACEHOLDER', "REDIS_HOST=$REDIS_IP"
} | Set-Content docker-compose.temp.yml

# Start the rest of the containers using the temporary file
Write-Host "Starting other containers with Redis IP: $REDIS_IP" -ForegroundColor Yellow
docker-compose -f docker-compose.temp.yml up -d app worker-manager audio-worker

# Clean up the temporary file
Remove-Item docker-compose.temp.yml

Write-Host ""
Write-Host "=== Language Tutor Application Started ===" -ForegroundColor Green
Write-Host "Redis IP: $REDIS_IP" -ForegroundColor Cyan
Write-Host "To view logs, run: docker-compose logs -f" -ForegroundColor Cyan
Write-Host "To stop the application, run: docker-compose down" -ForegroundColor Cyan