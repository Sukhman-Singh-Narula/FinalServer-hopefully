# Modifications needed for app/redis/audio_processor.py

"""
This file provides the changes needed to update the existing audio_processor.py file
to integrate with the agent_worker.py functionality.

Replace or merge these functions with your existing code.
"""

# Add to imports:
from app.agent_worker import (
    initialize_agent_session, 
    process_audio, 
    end_agent_session
)

# Updated process_user_audio_chunk function with agent integration
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
        # Process the audio buffer
        buffer_result = process_audio_buffer(session_id, device_id)
        
        # Get the buffer data before clearing it
        buffer_data = redis_conn.get(buffer_key)
        
        # Create a key for the agent to process
        agent_audio_key = f"agent:audio:{session_id}:{time.time()}"
        redis_conn.set(agent_audio_key, buffer_data, ex=300)  # 5 min expiration
        
        # Queue the buffer for processing by the agent worker
        agent_queue = Queue('agent_processing', connection=redis_conn)
        agent_job = agent_queue.enqueue(
            'app.agent_worker.process_audio',
            session_id=session_id,
            audio_key=agent_audio_key,
            job_id=f"agent_job_{session_id}_{time.time()}"
        )
        
        logger.info(f"Queued agent processing job {agent_job.id} for session {session_id}")
        
        # Clear the buffer for the next chunk
        redis_conn.set(buffer_key, b"")
        
        return {
            "status": "processed_with_agent",
            "session_id": session_id,
            "device_id": device_id,
            "buffer_size": buffer_size,
            "agent_job_id": agent_job.id,
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

# Updated process_audio_buffer function
def process_audio_buffer(session_id, device_id):
    """Process the accumulated audio buffer when it reaches sufficient size"""
    logger.info(f"Processing complete audio buffer for session {session_id}")
    
    # Get the buffer data
    buffer_key = f"buffer:{session_id}"
    buffer_data = redis_conn.get(buffer_key)
    
    if not buffer_data or len(buffer_data) == 0:
        logger.warning(f"Empty buffer for session {session_id}")
        return {"status": "empty_buffer"}
    
    # Convert PCM data to WAV for analysis
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
    
    # Don't clear the buffer here - it will be processed by the agent worker
    # and cleared after that
    
    return result

# Updated start_user_session_processor function
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
        'app.agent_worker.initialize_agent_session',
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

# Updated end_stream_processing function
def end_stream_processing(session_id, device_id, reason="client_signal"):
    """End the audio stream processing and process any remaining buffer"""
    logger.info(f"Ending stream processing for session {session_id}, device {device_id}. Reason: {reason}")
    
    # Process any remaining audio in the buffer
    buffer_key = f"buffer:{session_id}"
    if redis_conn.exists(buffer_key) and redis_conn.strlen(buffer_key) > 0:
        result = process_audio_buffer(session_id, device_id)
        
        # Get the buffer data
        buffer_data = redis_conn.get(buffer_key)
        
        # Create a key for the agent to process
        agent_audio_key = f"agent:audio:{session_id}:{time.time()}"
        redis_conn.set(agent_audio_key, buffer_data, ex=300)
        
        # Queue final buffer for processing
        agent_queue = Queue('agent_processing', connection=redis_conn)
        agent_job = agent_queue.enqueue(
            'app.agent_worker.process_audio',
            session_id=session_id,
            audio_key=agent_audio_key,
            job_id=f"final_agent_{session_id}_{time.time()}"
        )
        
        logger.info(f"Queued final agent processing job {agent_job.id}")
        
        # Clear the buffer
        redis_conn.set(buffer_key, b"")
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
        'app.agent_worker.end_agent_session',
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