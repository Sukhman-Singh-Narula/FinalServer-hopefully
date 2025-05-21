# app/agent_worker.py
import logging
import json
import time
import asyncio
from typing import Dict, List, Optional, AsyncGenerator, Any
import redis
from rq import Queue
from io import BytesIO
import wave

from app.syllabus_manager import SyllabusManager
from app.firebase_service import get_user_from_firestore, add_user_to_firestore
from app.openai_service import (
    transcribe_audio, 
    generate_response, 
    generate_streaming_response,
    generate_speech
)
from app.config import SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH, REDIS_HOST, REDIS_PORT, REDIS_DB
from app.spanish_workflow import SpanishWorkflow

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

def pcm_to_wav(pcm_bytes: bytes) -> bytes:
    """Convert PCM data to WAV format."""
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm_bytes)
    return wav_buffer.getvalue()
    # Keeping the remainder of the AgentSession class unchanged for brevity

def process_audio(session_id: str, audio_key: str) -> Dict:
    """
    Process audio data for a session
    
    Args:
        session_id: Session ID
        audio_key: Redis key for audio data
        
    Returns:
        Processing result
    """
    try:
        # Get audio data from Redis
        audio_data = redis_conn.get(audio_key)
        if not audio_data:
            logger.warning(f"Audio data not found for key: {audio_key}")
            return {"status": "error", "message": "Audio data not found"}
        
        # Get session information
        session_info_key = f"session:info:{session_id}"
        session_info = redis_conn.get(session_info_key)
        
        if not session_info:
            logger.warning(f"Session info not found: {session_id}")
            return {"status": "error", "message": "Session info not found"}
        
        session_data = json.loads(session_info)
        device_id = session_data.get("device_id", "unknown")
        
        # Create event loop for async calls
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Convert PCM to WAV format for transcription
        wav_audio = pcm_to_wav(audio_data)
        
        # Transcribe audio using OpenAI Whisper
        transcription = loop.run_until_complete(transcribe_audio(wav_audio))
        
        if not transcription:
            logger.warning(f"Failed to transcribe audio for session {session_id}")
            return {"status": "error", "message": "Failed to transcribe audio"}
        
        # Get or create agent session
        agent_session = AgentSession.load_from_redis(session_id)
        if not agent_session:
            # Create new session
            agent_session = AgentSession(session_id, device_id)
            loop.run_until_complete(agent_session.initialize())
        
        # Process transcription with the agent
        response_chunks = []
        async def collect_response():
            async for chunk in agent_session.process_transcription(transcription):
                response_chunks.append(chunk)
        
        loop.run_until_complete(collect_response())
        
        # Join response chunks
        response_text = "".join(response_chunks)
        
        # Store the result
        result = {
            "status": "success",
            "session_id": session_id,
            "device_id": device_id,
            "transcription": transcription,
            "response": response_text,
            "timestamp": time.time()
        }
        
        # Store in Redis
        result_key = f"agent:result:{session_id}:{time.time()}"
        redis_conn.set(result_key, json.dumps(result), ex=3600)
        
        # Publish event for realtime updates
        redis_conn.publish(
            f"agent:updates:{session_id}",
            json.dumps({
                "type": "response",
                "data": result
            })
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing audio: {e}")
        return {"status": "error", "message": str(e)}

def initialize_agent_session(session_id: str, device_id: str, user_id: Optional[str] = None) -> Dict:
    """
    Initialize agent session for a user
    
    Args:
        session_id: Session ID
        device_id: Device ID
        user_id: Optional user ID (defaults to device_id)
        
    Returns:
        Initialization result
    """
    try:
        # Create event loop for async calls
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create agent session
        session = AgentSession(session_id, device_id, user_id)
        initialized = loop.run_until_complete(session.initialize())
        
        if not initialized:
            logger.error(f"Failed to initialize agent session {session_id}")
            return {"status": "error", "message": "Failed to initialize agent session"}
        
        # Get the greeting message
        greeting = session.message_history[0]["content"] if session.message_history else "¡Hola!"
        
        # Generate speech from greeting
        # In a real implementation, this would convert the greeting to audio
        # speech_data = loop.run_until_complete(generate_speech(greeting))
        
        return {
            "status": "success",
            "session_id": session_id,
            "device_id": device_id,
            "user_id": session.user_id,
            "greeting": greeting,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Error initializing agent session: {e}")
        return {"status": "error", "message": str(e)}

def end_agent_session(session_id: str, reason: str = "client_request") -> Dict:
    """
    End agent session
    
    Args:
        session_id: Session ID
        reason: Reason for ending the session
        
    Returns:
        Result of ending the session
    """
    try:
        # Load session from Redis
        session_data = redis_conn.get(f"agent_session:{session_id}")
        if not session_data:
            logger.warning(f"Session {session_id} not found in Redis")
            return {"status": "error", "message": "Session not found"}
        
        # Parse session data
        state = json.loads(session_data)
        
        # Update state
        state["active"] = False
        state["end_time"] = time.time()
        state["end_reason"] = reason
        
        # Store updated state with shorter expiration
        redis_conn.set(
            f"agent_session:{session_id}", 
            json.dumps(state),
            ex=1800  # 30 minutes expiration
        )
        
        # Publish event for realtime updates
        redis_conn.publish(
            f"agent:updates:{session_id}",
            json.dumps({
                "type": "session_ended",
                "data": {
                    "session_id": session_id,
                    "reason": reason,
                    "timestamp": time.time()
                }
            })
        )
        
        return {
            "status": "success",
            "session_id": session_id,
            "message": f"Session ended: {reason}",
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Error ending agent session: {e}")
        return {"status": "error", "message": str(e)}