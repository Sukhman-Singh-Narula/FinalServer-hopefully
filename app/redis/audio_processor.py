# app/audio_processor.py
import logging
import time
import json
import redis
from rq import Queue, get_current_job

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Redis connection for workers
redis_client = redis.Redis(host='localhost', port=6379, db=0)

def start_stream_processor(session_id):
    """
    Long-running function that processes a specific user's audio stream.
    This function continuously checks the session's queue for new audio chunks.
    """
    logger.info(f"Starting stream processor for session {session_id}")
    
    # Get the current job to access metadata
    job = get_current_job()
    
    # Create a reference to this session's queue
    session_queue_name = f"stream_{session_id}"
    session_queue = Queue(session_queue_name, connection=redis_client)
    
    # Track the stream state
    stream_state = {
        "session_id": session_id,
        "active": True,
        "chunks_processed": 0,
        "last_activity": time.time(),
        "buffer": bytearray()  # For accumulating audio data if needed
    }
    
    # Store stream state in Redis so other processes can access it
    redis_client.set(
        f"stream_state:{session_id}",
        json.dumps({
            "active": True,
            "chunks_processed": 0,
            "last_activity": time.time()
        }),
        ex=3600  # 1 hour expiration
    )
    
    logger.info(f"Stream processor for {session_id} initialized and waiting for audio chunks")
    
    # Now keep processing from the queue until we're signaled to stop
    # This will be handled by the RQ worker process
    return {
        "status": "initialized", 
        "session_id": session_id,
        "queue": session_queue_name
    }

def process_audio_chunk(audio_key, session_id, device_id, chunk_id, timestamp):
    """Process a single audio chunk from the session's stream"""
    logger.info(f"Processing audio chunk {chunk_id} for session {session_id}")
    
    # Get the audio data from Redis
    audio_data = redis_client.get(audio_key)
    
    if not audio_data:
        logger.warning(f"Audio data not found for key: {audio_key}")
        return {"status": "error", "message": "Audio data not found"}
    
    # Update stream state
    stream_state_key = f"stream_state:{session_id}"
    stream_state_json = redis_client.get(stream_state_key)
    
    if stream_state_json:
        try:
            stream_state = json.loads(stream_state_json)
            stream_state["chunks_processed"] += 1
            stream_state["last_activity"] = time.time()
            
            # Update the state in Redis
            redis_client.set(
                stream_state_key,
                json.dumps(stream_state),
                ex=3600  # 1 hour expiration
            )
        except Exception as e:
            logger.error(f"Error updating stream state: {e}")
    
    # Here you would process the audio chunk
    # For this example, we're just logging the data size
    logger.info(f"Processed audio chunk: {len(audio_data)} bytes")
    
    # Optional: You could append this chunk to an accumulating buffer
    buffer_key = f"stream_buffer:{session_id}"
    redis_client.append(buffer_key, audio_data)
    redis_client.expire(buffer_key, 3600)  # 1 hour expiration
    
    # If you want to check if enough audio has accumulated for processing:
    buffer_size = redis_client.strlen(buffer_key)
    
    # If we've accumulated enough audio, process the buffer
    # For example, if we have at least 5 seconds of audio (assuming 16kHz, 16-bit):
    if buffer_size >= 160000:  # 16000 samples/sec * 2 bytes/sample * 5 seconds
        process_audio_buffer(session_id, buffer_key)
    
    return {
        "status": "processed",
        "chunk_id": chunk_id,
        "session_id": session_id,
        "bytes_processed": len(audio_data)
    }

def process_audio_buffer(session_id, buffer_key):
    """Process accumulated audio buffer when it reaches sufficient size"""
    logger.info(f"Processing complete audio buffer for session {session_id}")
    
    # Get the accumulated audio buffer
    audio_buffer = redis_client.get(buffer_key)
    
    if not audio_buffer:
        logger.warning(f"Audio buffer not found for key: {buffer_key}")
        return
    
    # Here you would process the complete audio buffer
    # For example, send it to a speech recognition service
    
    # After processing, clear the buffer to start fresh
    redis_client.delete(buffer_key)
    
    logger.info(f"Processed and cleared audio buffer: {len(audio_buffer)} bytes")

def end_stream_processing(session_id, device_id, reason="client_signal"):
    """Signal that the audio stream has ended"""
    logger.info(f"Ending stream processing for session {session_id}. Reason: {reason}")
    
    # Update stream state to inactive
    stream_state_key = f"stream_state:{session_id}"
    stream_state_json = redis_client.get(stream_state_key)
    
    if stream_state_json:
        try:
            stream_state = json.loads(stream_state_json)
            stream_state["active"] = False
            stream_state["end_reason"] = reason
            stream_state["end_time"] = time.time()
            
            # Update the state in Redis
            redis_client.set(
                stream_state_key,
                json.dumps(stream_state),
                ex=3600  # Keep for 1 hour after end
            )
        except Exception as e:
            logger.error(f"Error updating stream state: {e}")
    
    # Process any remaining audio in the buffer
    buffer_key = f"stream_buffer:{session_id}"
    if redis_client.exists(buffer_key):
        process_audio_buffer(session_id, buffer_key)
    
    # Clean up any other session resources if needed
    
    return {
        "status": "ended",
        "session_id": session_id,
        "reason": reason
    }