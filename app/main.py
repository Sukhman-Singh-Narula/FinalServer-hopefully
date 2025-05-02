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

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, background_tasks: BackgroundTasks):
    await websocket.accept()
    
    # Generate a unique session ID
    session_id = f"session:{user_id}:{int(asyncio.get_event_loop().time())}"
    
    # Store connection
    active_connections[session_id] = {
        "websocket": websocket,
        "user_id": user_id,
        "last_activity": asyncio.get_event_loop().time()
    }
    
    logger.info(f"Client connected: {user_id}, session: {session_id}")
    
    try:
        # Get Redis client
        redis = await get_redis_client()
        
        # Check for cached user data
        user_data_bytes = await redis.get(f"user:{user_id}")
        
        if user_data_bytes:
            user_data = json.loads(user_data_bytes)
            logger.info(f"Found cached user data for {user_id}")
        else:
            # Get from Firebase
            user_data = await get_user_from_firestore(user_id)
            if user_data:
                # Cache in Redis
                await redis.set(
                    f"user:{user_id}", 
                    json.dumps(user_data),
                    ex=3600  # 1 hour expiration
                )
        
        # Create PubSub for responses
        pubsub = await get_redis_pubsub()
        await pubsub.subscribe(f"responses:{session_id}")
        
        # Start background listener for responses
        background_tasks.add_task(
            handle_pubsub_messages,
            pubsub,
            websocket
        )
        
        # Send welcome message
        welcome_msg = f"Connected to Language Tutor. User: {user_data.get('name', 'Friend')}"
        await websocket.send_json({"type": "message", "text": welcome_msg})
        
        # Process WebSocket messages
        while True:
            data = await websocket.receive()
            
            if "bytes" in data:
                # Handle binary audio data
                audio_bytes = data["bytes"]
                
                # Store in Redis and publish for processing
                audio_key = f"audio:{session_id}:{asyncio.get_event_loop().time()}"
                await redis.set(audio_key, audio_bytes, ex=60)  # 60s expiration
                
                # Publish notification for processing
                await redis.publish(
                    "audio:processing",
                    json.dumps({
                        "session_id": session_id,
                        "audio_key": audio_key,
                        "user_id": user_id,
                        "timestamp": asyncio.get_event_loop().time()
                    })
                )
                
            elif "text" in data:
                # Handle text messages (commands)
                try:
                    message = json.loads(data["text"])
                    logger.info(f"Received message: {message}")
                    
                    # Process command
                    if message.get("type") == "command":
                        # Handle command
                        pass
                        
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {user_id}")
        # Clean up
        if session_id in active_connections:
            del active_connections[session_id]
        
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        # Clean up
        if session_id in active_connections:
            del active_connections[session_id]

async def handle_pubsub_messages(pubsub, websocket):
    """Background task to handle Redis PubSub messages"""
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                # Parse message data
                data = json.loads(message["data"])
                
                if data.get("type") == "audio_response":
                    # Get audio data from Redis
                    redis = await get_redis_client()
                    audio_key = data.get("audio_key")
                    if audio_key:
                        audio_data = await redis.get(audio_key)
                        if audio_data:
                            # Send audio to client
                            await websocket.send_bytes(audio_data)
                            # Clean up Redis
                            await redis.delete(audio_key)
                else:
                    # Forward other messages to client
                    await websocket.send_json(data)
    
    except asyncio.CancelledError:
        # Task was cancelled, exit gracefully
        await pubsub.unsubscribe()
    
    except Exception as e:
        logger.error(f"Error in pubsub handler: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)