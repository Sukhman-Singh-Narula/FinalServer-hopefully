FROM ubuntu:22.04

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3.9 \
    python3-pip \
    python3-venv \
    ffmpeg \
    redis-tools \
    sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Use Python 3.9 as default python via Debian alternatives system
RUN ln -s /usr/bin/python3.9 /usr/bin/python


# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command (can be overridden in docker-compose.yml)
CMD ["python", "run.py"]