# start_workers.py
import os
import sys
import subprocess
import logging
import signal
import time

# Configure logging - minimal output
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Worker manager process
worker_manager_process = None

def start_worker_manager():
    """Start the worker manager as a subprocess"""
    global worker_manager_process
    
    print("Starting worker manager...")
    
    # Start the worker manager with minimal output
    worker_manager_process = subprocess.Popen(
        [sys.executable, "app/redis/worker_manager.py"],
        stdout=subprocess.DEVNULL,  # Suppress standard output
        stderr=subprocess.PIPE,      # Only capture errors
        universal_newlines=True,
        bufsize=1
    )
    
    print(f"Worker manager started with PID: {worker_manager_process.pid}")
    
    # Return the process
    return worker_manager_process

def monitor_process_output(process):
    """Monitor for critical errors only"""
    while True:
        error = process.stderr.readline()
        if error == '' and process.poll() is not None:
            break
        
        if error and 'ERROR' in error:
            print(f"ERROR: {error.strip()}")
    
    # Process has terminated
    exit_code = process.poll()
    print(f"Process exited with return code: {exit_code}")
    return exit_code

def handle_signal(signum, frame):
    """Handle termination signals"""
    global worker_manager_process
    
    print(f"Received signal {signum}, shutting down...")
    
    if worker_manager_process:
        print(f"Terminating worker manager (PID: {worker_manager_process.pid})")
        try:
            worker_manager_process.terminate()
            time.sleep(2)
            if worker_manager_process.poll() is None:
                worker_manager_process.kill()
        except:
            pass
    
    sys.exit(0)

if __name__ == "__main__":
    print("Starting worker system...")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    
    try:
        # Start worker manager
        process = start_worker_manager()
        
        # Only monitor for errors
        monitor_process_output(process)
        
        # If we get here, worker manager exited
        print("Worker manager exited - restarting...")
        
        # Try to restart it
        while True:
            print("Restarting worker manager...")
            time.sleep(5)
            process = start_worker_manager()
            monitor_process_output(process)
    
    except KeyboardInterrupt:
        print("Keyboard interrupt received, shutting down...")
        handle_signal(signal.SIGINT, None)
    
    except Exception as e:
        print(f"Error in main process: {e}")
        handle_signal(signal.SIGTERM, None)