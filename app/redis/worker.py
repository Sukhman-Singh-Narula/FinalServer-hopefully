# app/redis/worker.py
import json
import logging
import time
import os
from redis import Redis
from rq import Queue, SimpleWorker
from rq.job import Job
from io import BytesIO
import wave
from app.config import REDIS_HOST, REDIS_PORT, REDIS_DB

from app.config import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)
from app.redis.redis_client import get_sync_redis_client

redis_conn = get_sync_redis_client()

# Function to start a worker for a specific queue
def start_worker(queue_names):
    """Start a worker to process jobs from the specified queues"""
    logger.info(f"Starting worker for queues: {', '.join(queue_names)}")
    
    # Create worker with explicit connection
    redis_client = get_sync_redis_client()
    worker = SimpleWorker(
    [Queue(name, connection=redis_client) for name in queue_names],
    connection=redis_client
    )
    
    # Start processing jobs
    logger.info(f"Worker listening on queues: {', '.join(queue_names)}")
    worker.work()

# Function to start an audio worker process
async def start_audio_worker():
    """Start the audio worker process asynchronously"""
    import asyncio
    import multiprocessing
    
    logger.info("Starting audio worker process...")
    
    # Create and start worker in a separate process
    process = multiprocessing.Process(
        target=start_worker,
        args=(['audio_processing'],)
    )
    process.start()
    
    logger.info(f"Audio worker process started with PID: {process.pid}")
    return process

# Main worker entry point
if __name__ == "__main__":
    logger.info("Starting Redis Queue worker...")
    
    # Define which queues to listen to
    queues = ['audio_processing']
    
    # Start the worker with explicit connection
    start_worker(queues)