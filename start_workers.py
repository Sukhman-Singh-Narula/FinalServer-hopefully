# start_workers.py
import os
import sys
import subprocess
import logging
import signal
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Worker manager process
worker_manager_process = None

def start_worker_manager():
    """Start the worker manager as a subprocess"""
    global worker_manager_process
    
    logger.info("Starting worker manager...")
    
    # Start the worker manager
    worker_manager_process = subprocess.Popen(
        [sys.executable, "app/redis/worker_manager.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    logger.info(f"Worker manager started with PID: {worker_manager_process.pid}")
    
    # Return the process
    return worker_manager_process

def monitor_process_output(process):
    """Monitor and log output from a subprocess"""
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            logger.info(output.strip())
    
    # Process has terminated
    rc = process.poll()
    logger.info(f"Process exited with return code: {rc}")
    return rc

def handle_signal(signum, frame):
    """Handle termination signals"""
    global worker_manager_process
    
    logger.info(f"Received signal {signum}, shutting down...")
    
    if worker_manager_process:
        logger.info(f"Terminating worker manager (PID: {worker_manager_process.pid})")
        try:
            worker_manager_process.terminate()
            # Wait a bit for graceful shutdown
            time.sleep(2)
            # Force kill if still running
            if worker_manager_process.poll() is None:
                worker_manager_process.kill()
        except:
            pass
    
    sys.exit(0)

if __name__ == "__main__":
    logger.info("Starting worker system...")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    try:
        # Start worker manager
        process = start_worker_manager()
        
        # Monitor its output
        monitor_process_output(process)
        
        # If we get here, worker manager exited
        logger.error("Worker manager exited unexpectedly")
        
        # Try to restart it
        while True:
            logger.info("Restarting worker manager in 5 seconds...")
            time.sleep(5)
            process = start_worker_manager()
            monitor_process_output(process)
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        handle_signal(signal.SIGINT, None)
    
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        # Try to clean up
        handle_signal(signal.SIGTERM, None)