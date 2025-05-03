# app/worker.py
import json
import logging
import time
import os
from redis import Redis
from rq import Worker, Queue
from rq.job import Job

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = Redis(host='localhost', port=6379, db=0)

# Audio buffer management
def process_audio_chunk(session_id, device_id, audio_key):
    """Process a single audio chunk from Redis"""
    logger.info(f"Processing audio chunk for session {session_id}, device {device_id}")
    
    # Get the audio data from Redis
    audio_data = redis_conn.get(audio_key)
    
    if not audio_data:
        logger.warning(f"Audio data not found for key: {audio_key}")
        return {"status": "error", "message": "Audio data not found"}
    
    # Get or create session buffer
    buffer_key = f"buffer:{session_id}"
    if not redis_conn.exists(buffer_key):
        redis_conn.set(buffer_key, b"", ex=3600)  # 1 hour expiration
    
    # Append audio data to buffer
    redis_conn.append(buffer_key, audio_data)
    
    # Update session metadata
    metadata_key = f"metadata:{session_id}"
    metadata = {
        "device_id": device_id,
        "last_activity": time.time(),
        "chunks_processed": 1
    }
    
    if redis_conn.exists(metadata_key):
        try:
            existing_metadata = json.loads(redis_conn.get(metadata_key))
            existing_metadata["last_activity"] = time.time()
            existing_metadata["chunks_processed"] += 1
            metadata = existing_metadata
        except:
            pass
    
    redis_conn.set(metadata_key, json.dumps(metadata), ex=3600)
    
    # Check if buffer is large enough to process
    buffer_size = redis_conn.strlen(buffer_key)
    logger.info(f"Buffer size for session {session_id}: {buffer_size} bytes")
    
    # Process buffer when it reaches threshold (e.g., 2 seconds of audio at 16kHz)
    if buffer_size >= 64000:  # Adjust threshold based on your requirements
        return process_audio_buffer(session_id, device_id)
    
    return {
        "status": "chunk_processed",
        "session_id": session_id,
        "device_id": device_id,
        "buffer_size": buffer_size
    }

def process_audio_buffer(session_id, device_id):
    """Process accumulated audio buffer"""
    logger.info(f"Processing complete audio buffer for session {session_id}")
    
    # Get the buffer
    buffer_key = f"buffer:{session_id}"
    buffer_data = redis_conn.get(buffer_key)
    
    if not buffer_data or len(buffer_data) == 0:
        logger.warning(f"Empty buffer for session {session_id}")
        return {"status": "empty_buffer"}
    
    # Here you would process the audio data
    # For example, convert to WAV, transcribe with Whisper, etc.
    logger.info(f"Processing {len(buffer_data)} bytes of audio data")
    
    # For demo purposes, just log the size
    result = {
        "status": "buffer_processed",
        "session_id": session_id,
        "device_id": device_id,
        "processed_bytes": len(buffer_data)
    }
    
    # Save processing result to Redis
    result_key = f"result:{session_id}:{time.time()}"
    redis_conn.set(result_key, json.dumps(result), ex=3600)
    
    # Clear the buffer after processing
    redis_conn.set(buffer_key, b"")
    
    return result

def end_session(session_id, device_id, reason="client_request"):
    """End audio processing session"""
    logger.info(f"Ending session {session_id} for device {device_id}. Reason: {reason}")
    
    # Process any remaining audio in the buffer
    result = process_audio_buffer(session_id, device_id)
    
    # Update session status
    metadata_key = f"metadata:{session_id}"
    if redis_conn.exists(metadata_key):
        try:
            metadata = json.loads(redis_conn.get(metadata_key))
            metadata["status"] = "ended"
            metadata["end_reason"] = reason
            metadata["end_time"] = time.time()
            redis_conn.set(metadata_key, json.dumps(metadata), ex=3600)
        except:
            pass
    
    # Return final status
    return {
        "status": "session_ended",
        "session_id": session_id,
        "device_id": device_id,
        "reason": reason,
        "final_processing": result
    }

# Function to start a worker for a specific queue
def start_worker(queue_names):
    """Start a worker to process jobs from the specified queues"""
    logger.info(f"Starting worker for queues: {', '.join(queue_names)}")
    
    # Create worker with explicit connection
    worker = Worker(
        [Queue(name, connection=redis_conn) for name in queue_names],
        connection=redis_conn
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