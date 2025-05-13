# app/audio_processor.py
import logging
import time
import json
import redis
from io import BytesIO
import wave

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = redis.Redis(host='localhost', port=6379, db=0)

# Audio settings
SAMPLE_RATE = 8000
CHANNELS = 1
SAMPLE_WIDTH = 2

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
    
    # Get user ID from session info
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
    
    # Get current stats
    stats = redis_conn.hgetall(stats_key)
    
    # Convert byte keys/values to strings/numbers
    formatted_stats = {}
    for k, v in stats.items():
        key = k.decode('utf-8') if isinstance(k, bytes) else k
        try:
            # Try to convert to number if possible
            value = float(v) if isinstance(v, bytes) else v
            # Convert timestamps to readable format
            if "time" in key and not isinstance(v, bytes):
                time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))
                formatted_stats[f"{key}_str"] = time_str
        except:
            value = v.decode('utf-8') if isinstance(v, bytes) else v
        
        formatted_stats[key] = value
    
    # Display stats
    logger.info(f"Session {session_id} stats: Chunks processed: {formatted_stats.get('chunks_processed', 0)}, "
               f"Last chunk size: {formatted_stats.get('last_chunk_size', 0)} bytes")
    
    # Add this chunk to the accumulated buffer
    buffer_key = f"buffer:{session_id}"
    redis_conn.append(buffer_key, audio_data)
    redis_conn.expire(buffer_key, 3600)  # 1 hour expiration
    
    # Get the current buffer size
    buffer_size = redis_conn.strlen(buffer_key)
    logger.info(f"Buffer size for session {session_id}: {buffer_size} bytes")
    
    # If buffer reaches threshold, process it
    # Threshold: 2 seconds of audio at 8kHz, 16-bit mono = 32000 bytes
    if buffer_size >= 32000:
        return process_audio_buffer(session_id, device_id)
    
    return {
        "status": "processed",
        "session_id": session_id,
        "device_id": device_id,
        "chunk_size": len(audio_data),
        "buffer_size": buffer_size,
        "timestamp": timestamp
    }

def process_audio_buffer(session_id, device_id):
    """Process the accumulated audio buffer when it reaches sufficient size"""
    logger.info(f"Processing complete audio buffer for session {session_id}")
    
    # Get the buffer data
    buffer_key = f"buffer:{session_id}"
    buffer_data = redis_conn.get(buffer_key)
    
    if not buffer_data or len(buffer_data) == 0:
        logger.warning(f"Empty buffer for session {session_id}")
        return {"status": "empty_buffer"}
    
    # For this task, we just want to display information about the buffer
    # In a real implementation, you would use a speech-to-text service here
    
    # Convert PCM data to WAV for analysis (not actually using the WAV, just for stats)
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(buffer_data)
    
    # Calculate audio duration in seconds
    duration = len(buffer_data) / (SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)
    
    # Log the information
    logger.info(f"Audio buffer stats for {session_id}:")
    logger.info(f"  Buffer size: {len(buffer_data)} bytes")
    logger.info(f"  Duration: {duration:.2f} seconds")
    logger.info(f"  Sample rate: {SAMPLE_RATE} Hz, Channels: {CHANNELS}, Sample width: {SAMPLE_WIDTH} bytes")
    
    # Store processing result
    result_key = f"result:{session_id}:{time.time()}"
    result = {
        "status": "buffer_processed",
        "session_id": session_id,
        "device_id": device_id,
        "buffer_size": len(buffer_data),
        "duration": round(duration, 2),
        "timestamp": time.time(),
        "process_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
    }
    
    redis_conn.set(result_key, json.dumps(result), ex=3600)
    
    # Update session stats
    stats_key = f"stats:{session_id}"
    pipe = redis_conn.pipeline()
    pipe.hincrby(stats_key, "buffers_processed", 1)
    pipe.hset(stats_key, "last_buffer_size", len(buffer_data))
    pipe.hset(stats_key, "last_buffer_duration", round(duration, 2))
    pipe.hset(stats_key, "last_buffer_process_time", time.time())
    pipe.execute()
    
    # Clear the buffer for the next chunk of audio
    redis_conn.set(buffer_key, b"")
    
    return result

def end_stream_processing(session_id, device_id, reason="client_signal"):
    """End the audio stream processing and process any remaining buffer"""
    logger.info(f"Ending stream processing for session {session_id}, device {device_id}. Reason: {reason}")
    
    # Process any remaining audio in the buffer
    buffer_key = f"buffer:{session_id}"
    if redis_conn.exists(buffer_key) and redis_conn.strlen(buffer_key) > 0:
        result = process_audio_buffer(session_id, device_id)
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
    
    # Log the initialization
    logger.info(f"Initialized session processor for {device_id}. Ready to process audio.")
    
    return {
        "status": "initialized",
        "session_id": session_id,
        "device_id": device_id,
        "queue_name": queue_name
    }