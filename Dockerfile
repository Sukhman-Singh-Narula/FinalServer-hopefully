# Use an official Python base image with all dependencies pre-installed
FROM python:3.9-slim

# Set working directory - simple path to avoid Windows path issues
WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Copy just the requirements first
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Start with a clean COPY that doesn't try to preserve permissions
COPY . .

# Create directories
RUN mkdir -p /code/credentials

# Default command
CMD ["python", "app/main.py"]