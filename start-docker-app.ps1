# PowerShell script to start the Language Tutor application using Docker
# This approach avoids building custom images and instead mounts the code directly

Write-Host "Starting Language Tutor application..." -ForegroundColor Cyan

# Check if .env file exists
if (-not (Test-Path -Path ".\.env" -PathType Leaf)) {
    # Create default .env file
    @"
# OpenAI API key
OPENAI_API_KEY=your_openai_api_key_here

# Redis configuration (only change if not using Docker)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Firebase configuration
FIREBASE_CREDENTIALS_PATH=/code/credentials/firebase-credentials.json
"@ | Set-Content -Path ".\.env" -NoNewline
    
    Write-Host "Created default .env file. Please edit it to add your OpenAI API key." -ForegroundColor Yellow
    Write-Host "Press any key to continue after editing the .env file..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# Create credentials directory if it doesn't exist
if (-not (Test-Path -Path ".\credentials" -PathType Container)) {
    New-Item -Path ".\credentials" -ItemType Directory | Out-Null
    Write-Host "Created credentials directory. Please add your Firebase credentials file to it." -ForegroundColor Yellow
    Write-Host "Press any key to continue after adding the credentials file..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# Create requirements.txt if it doesn't exist
if (-not (Test-Path -Path ".\requirements.txt" -PathType Leaf)) {
    @"
fastapi==0.105.0
uvicorn==0.24.0
websockets==12.0
openai==1.3.6
redis==5.0.1
rq==1.15.1
firebase-admin==6.2.0
pydub==0.25.1
numpy==1.26.2
python-dotenv==1.0.0
prettytable==3.9.0
sounddevice==0.4.6
wave==0.0.2
"@ | Set-Content -Path ".\requirements.txt" -NoNewline
    
    Write-Host "Created requirements.txt file." -ForegroundColor Green
}

# Start the application using Docker Compose
try {
    Write-Host "Starting Docker Compose services..." -ForegroundColor Cyan
    docker-compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Language Tutor application started successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Access the application at: http://localhost:8000" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Useful commands:" -ForegroundColor Yellow
        Write-Host "- View logs: docker-compose logs -f" -ForegroundColor Yellow
        Write-Host "- Stop application: docker-compose down" -ForegroundColor Yellow
    } else {
        Write-Host "Failed to start Docker Compose services. Check the errors above." -ForegroundColor Red
    }
} catch {
    Write-Host "An error occurred: $_" -ForegroundColor Red
}