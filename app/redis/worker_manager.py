# worker_manager.py
import os
import redis
import time
from rq import Worker, Queue, Connection
from redis import Redis

def start_worker_for_queue(queue_name):
    """Start a dedicated worker for a specific queue"""
    redis_conn = Redis(host='localhost', port=6379, db=0)
    
    with Connection(redis_conn):
        worker = Worker([queue_name])
        worker.work(burst=False)  # Run continuously

if __name__ == "__main__":
    redis_conn = Redis(host='localhost', port=6379, db=0)
    
    # Start the session management worker
    os.fork()
    if os.fork() == 0:
        start_worker_for_queue('session_management')
        exit()
    
    # Monitor for new user queues and start workers for them
    while True:
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
                
                # Fork a process for this worker
                if os.fork() == 0:
                    start_worker_for_queue(queue)
                    exit()
        
        time.sleep(5)  # Check for new queues every 5 seconds