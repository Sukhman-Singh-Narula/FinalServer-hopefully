# app/redis/worker_manager.py
import os
import time
import redis
import json
import logging
import signal
import sys
import traceback
from rq import Worker, Queue
from multiprocessing import Process
from app.config import REDIS_HOST, REDIS_PORT, REDIS_DB

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG for more details
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("worker_manager")

# Redis connection with error handling
try:
# Replace the existing Redis connection with:
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    # Verify Redis connection
    ping_result = redis_conn.ping()
    logger.info(f"Redis connection test: {ping_result}")
except Exception as e:
    logger.critical(f"Failed to connect to Redis: {e}", exc_info=True)
    sys.exit(1)

AGENT_WORKERS = int(os.getenv("AGENT_WORKERS", 2))
# Process tracking
worker_processes = {}

def custom_exception_handler(job, exc_type, exc_value, traceback_obj):
    """Custom exception handler for worker errors"""
    logger.error(f"JOB FAILURE: {job.id} (func: {job.func_name})")
    logger.error(f"EXCEPTION: {exc_type.__name__}: {exc_value}")
    
    # Format the traceback and log it
    tb_lines = traceback.format_exception(exc_type, exc_value, traceback_obj)
    logger.error("TRACEBACK:\n" + "".join(tb_lines))
    
    # Check for specific known issues
    if "ImportError" in exc_type.__name__ or "ModuleNotFoundError" in exc_type.__name__:
        logger.error("DIAGNOSIS: Import path issue detected. Check PYTHONPATH and module structure.")
    elif "ConnectionError" in exc_type.__name__ or "TimeoutError" in exc_type.__name__:
        logger.error("DIAGNOSIS: Redis connection issue detected.")
    elif "OSError" in exc_type.__name__ and "fork" in str(exc_value).lower():
        logger.error("DIAGNOSIS: Process forking issue detected in WSL.")
    
    # Save job info and error details to Redis for debugging
    try:
        job_data = {
            "id": job.id,
            "func": job.func_name,
            "args": job.args,
            "kwargs": job.kwargs,
            "error_type": exc_type.__name__,
            "error_msg": str(exc_value),
            "traceback": "".join(tb_lines),
            "timestamp": time.time()
        }
        redis_conn.set(
            f"debug:job_error:{job.id}", 
            json.dumps(job_data),
            ex=86400  # 24 hours expiration
        )
        logger.info(f"Saved job error details to Redis key: debug:job_error:{job.id}")
    except Exception as e:
        logger.error(f"Error saving job error details: {e}")
    
    return False  # Don't requeue the job

def start_worker_for_queue(queue_name):
    """Start a dedicated worker for a specific queue with enhanced error logging"""
    try:
        logger.info(f"Starting worker for queue: {queue_name}")
        
        # Log system info
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Python executable: {sys.executable}")
        logger.info(f"Current working directory: {os.getcwd()}")
        
        # Create a new Redis connection for this worker
        worker_redis = redis.Redis(host='localhost', port=6379, db=0)
        
        # Test Redis connection
        ping_result = worker_redis.ping()
        logger.info(f"Worker redis connection test: {ping_result}")
        
        # Create queue with explicit connection
        queue = Queue(queue_name, connection=worker_redis)
        
        # Create and start the worker with custom exception handling
        worker = Worker(
            [queue], 
            connection=worker_redis,
            exception_handlers=[custom_exception_handler],
            name=f"{queue_name}_worker_{os.getpid()}"
        )
        
        # Set up signal handlers for graceful shutdown
        def graceful_shutdown(signum, frame):
            logger.info(f"Received shutdown signal {signum}, stopping worker for {queue_name}")
            worker.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)
        
        # Start working
        logger.info(f"Worker listening on queue: {queue_name}")
        worker.work(burst=False)  # Run continuously
    
    except Exception as e:
        logger.critical(f"Error in worker process for {queue_name}: {e}", exc_info=True)
        sys.exit(1)

def monitor_user_queues():
    """Monitor for new user queues and start workers for them"""
    # Test Redis connection
    try:
        ping_result = redis_conn.ping()
        if not ping_result:
            logger.error("Redis connection test failed in monitor_user_queues")
            return
    except Exception as e:
        logger.error(f"Redis error in monitor_user_queues: {e}")
        return
    
    # Find all user queues
    try:
        user_queues = set()
        for key in redis_conn.keys('rq:queue:user_*'):
            queue_name = key.decode('utf-8').replace('rq:queue:', '')
            user_queues.add(queue_name)
        
        # Add agent queue if not already monitored
        agent_queue = 'agent_processing'
        if not any(key.startswith(agent_queue) for key in worker_processes.keys()):
            for i in range(AGENT_WORKERS):
                process = Process(
                    target=start_worker_for_queue,
                    args=(agent_queue,),
                    name=f"worker-{agent_queue}_{i}"
                )
                process.daemon = True
                process.start()
                logger.info(f"Started agent worker {i} with PID: {process.pid}")
                worker_processes[f'{agent_queue}_{i}'] = {
                    'process': process,
                    'start_time': time.time()
                }
        
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
    except Exception as e:
        logger.error(f"Error in monitor_user_queues: {e}", exc_info=True)

def check_worker_health():
    """Check if worker processes are still alive and restart if needed"""
    for queue_name, info in list(worker_processes.items()):
        process = info['process']
        try:
            if not process.is_alive():
                logger.warning(f"Worker for {queue_name} (PID: {process.pid}) died, restarting")
                
                # Get exit code if available
                exitcode = process.exitcode
                logger.warning(f"Worker exit code: {exitcode}")
                
                # Clean up the dead process
                del worker_processes[queue_name]
                
                # Remove worker key from Redis
                redis_conn.delete(f"worker:{queue_name}")
                
                # Let monitor_user_queues restart it
        except Exception as e:
            logger.error(f"Error checking process health for {queue_name}: {e}")

if __name__ == "__main__":
    logger.info("Starting worker manager...")
    
    # Verify Redis connection
    try:
        ping_result = redis_conn.ping()
        logger.info(f"Redis connection test: {ping_result}")
    except Exception as e:
        logger.critical(f"Failed to connect to Redis: {e}", exc_info=True)
        sys.exit(1)
    
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
    
    # Start workers for the agent processing queue
    for i in range(AGENT_WORKERS):
        agent_process = Process(
            target=start_worker_for_queue,
            args=('agent_processing',),
            name=f"worker-agent_processing_{i}"
        )
        agent_process.daemon = True
        agent_process.start()
        logger.info(f"Started agent processing worker {i} with PID: {agent_process.pid}")
        worker_processes[f'agent_processing_{i}'] = {
            'process': agent_process,
            'start_time': time.time()
        }
    
    try:
        # Monitor for new user queues and manage workers
        logger.info("Entering main monitoring loop")
        while True:
            try:
                monitor_user_queues()
                check_worker_health()
            except Exception as e:
                logger.error(f"Error in main monitoring loop: {e}", exc_info=True)
            time.sleep(5)  # Check every 5 seconds
    
    except KeyboardInterrupt:
        logger.info("Shutting down worker manager...")
        sys.exit(0)