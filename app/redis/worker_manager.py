# worker_manager.py
import os
import time
import redis
import json
import logging
import signal
import sys
from rq import Worker, Queue
from multiprocessing import Process

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = redis.Redis(host='localhost', port=6379, db=0)

# Process tracking
worker_processes = {}

def start_worker_for_queue(queue_name):
    """Start a dedicated worker for a specific queue"""
    try:
        logger.info(f"Starting worker for queue: {queue_name}")
        
        # Create a new Redis connection
        worker_redis = redis.Redis(host='localhost', port=6379, db=0)
        
        # Create queue with explicit connection
        queue = Queue(queue_name, connection=worker_redis)
        
        # Create and start the worker
        worker = Worker([queue], connection=worker_redis)
        
        # Set up signal handlers for graceful shutdown
        def graceful_shutdown(signum, frame):
            logger.info(f"Received shutdown signal, stopping worker for {queue_name}")
            worker.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)
        
        # Start working
        logger.info(f"Worker listening on queue: {queue_name}")
        worker.work(burst=False)  # Run continuously
    
    except Exception as e:
        logger.error(f"Error in worker process for {queue_name}: {e}")
        sys.exit(1)

def monitor_user_queues():
    """Monitor for new user queues and start workers for them"""
    # Find all user queues
    user_queues = set()
    for key in redis_conn.keys('rq:queue:user_*'):
        queue_name = key.decode('utf-8').replace('rq:queue:', '')
        user_queues.add(queue_name)
    
    # Start a worker for each user queue if not already running
    for queue in user_queues:
        worker_key = f"worker:{queue}"
        if not redis_conn.exists(worker_key):
            redis_conn.set(worker_key, "1", ex=3600)  # Mark worker as started
            
            # Start a new process for this worker
            process = Process(
                target=start_worker_for_queue,
                args=(queue,),
                name=f"worker-{queue}"
            )
            
            process.daemon = True  # Automatically terminate when main process exits
            process.start()
            
            logger.info(f"Started worker process for queue {queue} with PID: {process.pid}")
            
            # Track the process
            worker_processes[queue] = {
                'process': process,
                'start_time': time.time()
            }

def check_worker_health():
    """Check if worker processes are still alive and restart if needed"""
    for queue_name, info in list(worker_processes.items()):
        process = info['process']
        if not process.is_alive():
            logger.warning(f"Worker for {queue_name} (PID: {process.pid}) died, restarting")
            
            # Clean up the dead process
            del worker_processes[queue_name]
            
            # Remove worker key from Redis
            redis_conn.delete(f"worker:{queue_name}")
            
            # Let monitor_user_queues restart it

if __name__ == "__main__":
    logger.info("Starting worker manager...")
    
    # Start the session management worker
    session_process = Process(
        target=start_worker_for_queue,
        args=('session_management',),
        name="worker-session_management"
    )
    session_process.daemon = True
    session_process.start()
    logger.info(f"Started session management worker with PID: {session_process.pid}")
    worker_processes['session_management'] = {
        'process': session_process,
        'start_time': time.time()
    }
    
    # Start a worker for the main audio processing queue
    audio_process = Process(
        target=start_worker_for_queue,
        args=('audio_processing',),
        name="worker-audio_processing"
    )
    audio_process.daemon = True
    audio_process.start()
    logger.info(f"Started audio processing worker with PID: {audio_process.pid}")
    worker_processes['audio_processing'] = {
        'process': audio_process,
        'start_time': time.time()
    }
    
    try:
        # Monitor for new user queues and manage workers
        while True:
            monitor_user_queues()
            check_worker_health()
            time.sleep(5)  # Check every 5 seconds
    
    except KeyboardInterrupt:
        logger.info("Shutting down worker manager...")
        sys.exit(0)