import os
import time
import uvicorn
import wave
from io import BytesIO
from pydub import AudioSegment
import asyncio
import logging
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.redis_client import get_redis_client, get_redis_pubsub
from app.firebase_service import get_user_from_firestore
from app.worker import start_audio_worker
from app.config import FIREBASE_CREDENTIALS_PATH, SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(title="Language Tutor WebSocket Server")


FIREBASE_CREDENTIALS_PATH="./bern-8dbc2-firebase-adminsdk-fbsvc-f2d05b268c.json"
SAMPLE_RATE = 8000
CHANNELS = 1
SAMPLE_WIDTH = 2

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections = {}

def pcm_to_wav(pcm_bytes: bytes) -> bytes:
    """Convert PCM data to WAV format."""
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm_bytes)
    return wav_buffer.getvalue()

def mp3_to_wav(mp3_data: bytes) -> bytes:
    """Convert MP3 chunk to WAV (PCM 16-bit)."""
    mp3_buffer = BytesIO(mp3_data)
    audio = AudioSegment.from_file(mp3_buffer, format="mp3")
    wav_buffer = BytesIO()
    audio.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS).set_sample_width(SAMPLE_WIDTH)
    audio.export(wav_buffer, format="wav")
    return wav_buffer.getvalue()

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    # Close Redis connection if needed
    redis = await get_redis_client()
    await redis.close()
    
@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "ok"}

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await websocket.accept()
    
    # Generate a unique session ID
    session_id = f"session:{device_id}:{int(asyncio.get_event_loop().time())}"
    
    # Store connection
    active_connections[session_id] = {
        "websocket": websocket,
        "device_id": device_id,
        "last_activity": asyncio.get_event_loop().time()
    }
    
    logger.info(f"ESP device connected: {device_id}, session: {session_id}")
    
    try:
        # Get Redis client
        redis_client = await get_redis_client()
        
        # Process WebSocket messages
        while True:
            data = await websocket.receive()
            
            if "bytes" in data:
                # Handle binary audio data
                audio_bytes = data["bytes"]
                
                # Log audio chunk size
                logger.debug(f"Received audio chunk: {len(audio_bytes)} bytes")
                
                # Publish to Redis PubSub
                await redis_client.publish(
                    "audio:stream",
                    json.dumps({
                        "session_id": session_id,
                        "device_id": device_id,
                        "timestamp": asyncio.get_event_loop().time(),
                        "chunk_size": len(audio_bytes)
                    })
                )
                
                # Store actual audio bytes in Redis
                audio_key = f"audio:{session_id}:{asyncio.get_event_loop().time()}"
                await redis_client.set(audio_key, audio_bytes, ex=120)  # 60s expiration
                
                # Publish the key where the audio is stored
                await redis_client.publish(
                    "audio:keys",
                    json.dumps({
                        "session_id": session_id,
                        "device_id": device_id,
                        "audio_key": audio_key,
                        "timestamp": asyncio.get_event_loop().time()
                    })
                )
                
            elif "text" in data:
                # Handle text messages (commands)
                try:
                    message = json.loads(data["text"])
                    logger.info(f"Received message: {message}")
                    
                    # Process command if needed
                    command_type = message.get("type")
                    
                    if command_type == "end_stream":
                        # Signal end of audio stream
                        await redis_client.publish(
                            "audio:control",
                            json.dumps({
                                "session_id": session_id,
                                "device_id": device_id,
                                "command": "end_stream",
                                "timestamp": asyncio.get_event_loop().time()
                            })
                        )
                        await websocket.send_text(json.dumps({
                            "type": "info", 
                            "message": "Stream end acknowledged"
                        }))
                        
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    await websocket.send_text(json.dumps({
                        "type": "error", 
                        "message": "Invalid JSON"
                    }))
    
    except WebSocketDisconnect:
        logger.info(f"ESP device disconnected: {device_id}")
        # Clean up
        if session_id in active_connections:
            del active_connections[session_id]
        
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        # Clean up
        if session_id in active_connections:
            del active_connections[session_id]
@app.on_event("startup")
async def start_workers():
    asyncio.create_task(start_audio_worker())