# workers.py
import os
import sys
import logging
from redis import Redis
from rq import Worker, Queue, Connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = Redis(host='localhost', port=6379, db=0)

# Define which queues to listen to
QUEUES = ['audio_processing']

if __name__ == '__main__':
    logger.info("Starting RQ workers...")
    
    # Find all stream queues and add them to the list
    stream_keys = redis_conn.keys('rq:queue:stream_*')
    for key in stream_keys:
        queue_name = key.decode('utf-8').replace('rq:queue:', '')
        if queue_name not in QUEUES:
            QUEUES.append(queue_name)
            logger.info(f"Added stream queue: {queue_name}")
    
    with Connection(redis_conn):
        worker = Worker(QUEUES)
        logger.info(f"Worker listening on queues: {', '.join(QUEUES)}")
        worker.work(logging_level=logging.INFO)