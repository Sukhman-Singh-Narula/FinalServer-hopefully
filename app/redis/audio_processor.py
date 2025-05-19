# app/redis/audio_processor.py
import logging
import json
import time
from io import BytesIO
import wave
from redis import Redis
from rq import Queue

from app.config import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH
from app.agent_worker import process_audio, initialize_agent_session, end_agent_session
# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = Redis(host='localhost', port=6379, db=0)

def process_user_audio_chunk(session_id, audio_key, timestamp):
    """
    Process a single audio chunk for a user
    This function is called by the RQ worker when a job is processed
    """
    logger.info(f"Processing audio chunk {audio_key} for session {session_id}")
    
    # Get the audio data from Redis
    audio_data = redis_conn.get(audio_key)
    
    if not audio_data:
        logger.warning(f"Audio data not found for key: {audio_key}")
        return {"status": "error", "message": "Audio data not found"}
    
    # Get session info
    session_info_key = f"session:info:{session_id}"
    session_info = redis_conn.get(session_info_key)
    
    if not session_info:
        logger.warning(f"Session info not found: {session_id}")
        return {"status": "error", "message": "Session info not found"}
    
    try:
        session_data = json.loads(session_info)
        device_id = session_data.get("device_id", "unknown")
    except:
        device_id = "unknown"
    
    # Update session statistics
    stats_key = f"stats:{session_id}"
    pipe = redis_conn.pipeline()
    
    # Increment chunk count
    pipe.hincrby(stats_key, "chunks_processed", 1)
    pipe.hset(stats_key, "last_activity", time.time())
    pipe.hset(stats_key, "last_chunk_size", len(audio_data))
    
    # If this is the first chunk, initialize other stats
    if not redis_conn.exists(stats_key):
        pipe.hset(stats_key, "first_chunk_time", time.time())
        pipe.hset(stats_key, "device_id", device_id)
    
    # Execute all Redis commands
    pipe.execute()
    
    # Add this chunk to the accumulated buffer
    buffer_key = f"buffer:{session_id}"
    redis_conn.append(buffer_key, audio_data)
    redis_conn.expire(buffer_key, 3600)  # 1 hour expiration
    
    # Get the current buffer size
    buffer_size = redis_conn.strlen(buffer_key)
    logger.info(f"Buffer size for session {session_id}: {buffer_size} bytes")
    
    # If buffer reaches threshold, process it directly with agent
    # Threshold: 2 seconds of audio at 8kHz, 16-bit mono = 32000 bytes
    if buffer_size >= 32000:
        # Get the buffer data (we don't need to get it again but keeping for clarity)
        buffer_data = redis_conn.get(buffer_key)
        
        # Log audio stats
        duration = buffer_size / (SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)
        logger.info(f"Audio buffer stats for {session_id}:")
        logger.info(f"  Buffer size: {buffer_size} bytes")
        logger.info(f"  Duration: {duration:.2f} seconds")
        logger.info(f"  Sample rate: {SAMPLE_RATE} Hz, Channels: {CHANNELS}, Sample width: {SAMPLE_WIDTH} bytes")
        
        # Queue the buffer for processing by the agent worker
        agent_queue = Queue('agent_processing', connection=redis_conn)
        agent_job = agent_queue.enqueue(
            process_audio,
            session_id=session_id,
            audio_key=buffer_key,  # Use the buffer key directly
            job_id=f"agent_job_{session_id}_{time.time()}"
        )
        
        logger.info(f"Queued agent processing job {agent_job.id} for session {session_id}")
        
        # Update session stats
        pipe = redis_conn.pipeline()
        pipe.hincrby(stats_key, "buffers_processed", 1)
        pipe.hset(stats_key, "last_buffer_size", buffer_size)
        pipe.hset(stats_key, "last_buffer_duration", round(duration, 2))
        pipe.hset(stats_key, "last_buffer_process_time", time.time())
        pipe.execute()
        
        # Clear the buffer for the next chunk
        redis_conn.set(buffer_key, b"", ex=3600)
        
        return {
            "status": "processed_with_agent",
            "session_id": session_id,
            "device_id": device_id,
            "buffer_size": buffer_size,
            "agent_job_id": agent_job.id,
            "duration": round(duration, 2),
            "timestamp": timestamp
        }
    
    return {
        "status": "processed",
        "session_id": session_id,
        "device_id": device_id,
        "chunk_size": len(audio_data),
        "buffer_size": buffer_size,
        "timestamp": timestamp
    }

# Keep a deprecated version for backwards compatibility
def process_audio_buffer(session_id, device_id):
    """This function is now deprecated and only kept for metrics/logging compatibility"""
    logger.info(f"process_audio_buffer is deprecated, using direct agent processing for {session_id}")
    # Return a compatible result structure for any code that might still call this
    return {
        "status": "redirected_to_agent",
        "session_id": session_id,
        "device_id": device_id,
        "timestamp": time.time()
    }

def start_user_session_processor(device_id, session_id, queue_name):
    """Initialize session processing for a user"""
    logger.info(f"Starting session processor for device {device_id}, session {session_id}")
    
    # Create session state
    session_state_key = f"session:state:{session_id}"
    state = {
        "active": True,
        "start_time": time.time(),
        "device_id": device_id,
        "queue_name": queue_name
    }
    redis_conn.set(session_state_key, json.dumps(state), ex=3600)
    
    # Initialize statistics
    stats_key = f"stats:{session_id}"
    pipe = redis_conn.pipeline()
    pipe.hset(stats_key, "start_time", time.time())
    pipe.hset(stats_key, "device_id", device_id)
    pipe.hset(stats_key, "chunks_processed", 0)
    pipe.hset(stats_key, "buffers_processed", 0)
    pipe.execute()
    
    # Initialize agent session
    agent_queue = Queue('agent_processing', connection=redis_conn)
    agent_job = agent_queue.enqueue(
        initialize_agent_session,
        session_id=session_id,
        device_id=device_id,
        job_id=f"init_agent_{session_id}"
    )
    
    logger.info(f"Queued agent initialization job {agent_job.id} for session {session_id}")
    
    return {
        "status": "initialized",
        "session_id": session_id,
        "device_id": device_id,
        "queue_name": queue_name,
        "agent_job_id": agent_job.id
    }

def end_stream_processing(session_id, device_id, reason="client_signal"):
    """End the audio stream processing and process any remaining buffer"""
    logger.info(f"Ending stream processing for session {session_id}, device {device_id}. Reason: {reason}")
    
    # Process any remaining audio in the buffer
    buffer_key = f"buffer:{session_id}"
    if redis_conn.exists(buffer_key) and redis_conn.strlen(buffer_key) > 0:
        buffer_size = redis_conn.strlen(buffer_key)
        
        # Only process if buffer has meaningful content
        if buffer_size >= 8000:  # At least 0.5 seconds of audio
            # Queue final buffer for processing directly by agent
            agent_queue = Queue('agent_processing', connection=redis_conn)
            agent_job = agent_queue.enqueue(
                process_audio,
                session_id=session_id,
                audio_key=buffer_key,  # Use buffer key directly
                job_id=f"final_agent_{session_id}_{time.time()}"
            )
            
            logger.info(f"Queued final agent processing job {agent_job.id}")
        
        # Clear the buffer
        redis_conn.set(buffer_key, b"")
        
        result = {
            "status": "final_buffer_processed",
            "buffer_size": buffer_size
        }
    else:
        result = {"status": "no_remaining_buffer"}
    
    # Update session state
    session_state_key = f"session:state:{session_id}"
    state = {
        "active": False,
        "end_time": time.time(),
        "end_reason": reason,
        "device_id": device_id
    }
    redis_conn.set(session_state_key, json.dumps(state), ex=3600)
    
    # End agent session
    agent_queue = Queue('agent_processing', connection=redis_conn)
    agent_job = agent_queue.enqueue(
        end_agent_session,
        session_id=session_id,
        reason=reason,
        job_id=f"end_agent_{session_id}"
    )
    
    logger.info(f"Queued agent session end job {agent_job.id}")
    
    # Final session statistics
    stats_key = f"stats:{session_id}"
    if redis_conn.exists(stats_key):
        stats = redis_conn.hgetall(stats_key)
        
        # Convert byte keys/values to strings/numbers
        formatted_stats = {}
        for k, v in stats.items():
            key = k.decode('utf-8') if isinstance(k, bytes) else k
            try:
                # Try to convert to number
                value = float(v) if isinstance(v, bytes) else v
            except:
                value = v.decode('utf-8') if isinstance(v, bytes) else v
            
            formatted_stats[key] = value
        
        chunks_processed = formatted_stats.get('chunks_processed', 0)
        buffers_processed = formatted_stats.get('buffers_processed', 0)
        
        logger.info(f"Session {session_id} final stats:")
        logger.info(f"  Total chunks processed: {chunks_processed}")
        logger.info(f"  Total buffers processed: {buffers_processed}")
        logger.info(f"  Session end reason: {reason}")
        
    return {
        "status": "session_ended",
        "session_id": session_id,
        "device_id": device_id,
        "reason": reason,
        "final_result": result
    }