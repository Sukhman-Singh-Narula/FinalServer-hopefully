# run.py
import asyncio
import logging
import uvicorn
import subprocess
import sys
import os
import signal
import atexit
from app.main import app
from app.redis.redis_client import get_redis_client
from app.firebase_service import initialize_firebase

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Global variable to track worker process
worker_process = None

def start_worker_process():
    """Start the worker manager process"""
    global worker_process
    
    logger.info("Starting worker manager process...")
    
    # Start the worker process as a subprocess
    worker_process = subprocess.Popen(
        [sys.executable, "start_workers.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    logger.info(f"Worker manager started with PID: {worker_process.pid}")
    
    # Start a thread to monitor worker output
    import threading
    threading.Thread(
        target=monitor_worker_output,
        args=(worker_process,),
        daemon=True
    ).start()
    
    return worker_process

def monitor_worker_output(process):
    """Monitor and log output from the worker process"""
    for line in process.stdout:
        if line:
            logger.info(f"[Worker] {line.strip()}")
    
    # Process has terminated
    if process.poll() is not None:
        exit_code = process.poll()
        logger.warning(f"Worker process exited with return code: {exit_code}")

def cleanup_worker():
    """Clean up worker process on exit"""
    global worker_process
    
    if worker_process and worker_process.poll() is None:
        logger.info(f"Terminating worker process (PID: {worker_process.pid})")
        try:
            # Send SIGTERM to allow graceful shutdown
            worker_process.terminate()
            # Give it some time to shut down gracefully
            worker_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Force kill if it doesn't terminate in time
            logger.warning("Worker process did not terminate in time, forcing kill...")
            worker_process.kill()
        except Exception as e:
            logger.error(f"Error terminating worker process: {e}")

async def setup():
    """Perform setup tasks before starting server"""
    # Initialize Redis connection
    redis = await get_redis_client()
    
    # Initialize Firebase
    initialize_firebase()
    
    logging.info("Setup complete")

if __name__ == "__main__":
    # Run setup tasks
    asyncio.run(setup())
    
    # Start the worker process
    start_worker_process()
    
    # Register cleanup handler
    atexit.register(cleanup_worker)
    
    # Also handle signals
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        cleanup_worker()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start FastAPI server
        logger.info("Starting FastAPI server...")
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    finally:
        # Ensure workers are cleaned up
        cleanup_worker()