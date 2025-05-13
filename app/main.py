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
from app.redis.redis_client import get_redis_client, get_redis_pubsub
# from app.firebase_service import get_user_from_firestore
from app.redis.worker import start_audio_worker
from app.config import FIREBASE_CREDENTIALS_PATH, SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH
from redis import Redis
from rq import Queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000
CHANNELS = 1
SAMPLE_WIDTH = 2

redis_conn = Redis(host='localhost', port=6379, db=0)
app = FastAPI(title="Language Tutor WebSocket Server")
audio_queue = Queue('audio', connection=redis_conn)
stream_queues = {}
session_queue = Queue('session_management', connection=redis_conn)

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
    # Close Redis connection
    redis = await get_redis_client()
    
    # Cancel all running tasks
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()
    
    # Wait for all tasks to complete with a timeout
    await asyncio.gather(*asyncio.all_tasks(), return_exceptions=True)
    
    # Close Redis connection
    await redis.close()
    
@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "ok"}

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await websocket.accept()
    
    # Generate a unique session ID
    session_id = f"session:{device_id}:{int(time.time())}"
    session_id = session_id.replace(":", "_")
    logger.info(f"New WebSocket connection: device_id={device_id}, session_id={session_id}")
    
    # Create a dedicated queue for this user's audio
    user_queue_name = f"user_{device_id}"
    redis_conn = Redis(host='localhost', port=6379, db=0)
    user_queue = Queue(user_queue_name, connection=redis_conn)
    
    # Store session info in Redis
    redis_conn.set(f"session:info:{session_id}", 
                  json.dumps({
                      "device_id": device_id, 
                      "queue": user_queue_name,
                      "start_time": time.time()
                  }),
                  ex=3600)
    
    # Start a session processor for this user
    main_queue = Queue('session_management', connection=redis_conn)
    main_queue.enqueue(
        'app.audio_processor.start_user_session_processor',
        device_id=device_id,
        session_id=session_id,
        queue_name=user_queue_name,
        job_id=f"processor_{device_id}_{session_id}"
    )
    
    # Track this connection
    active_connections[session_id] = websocket
    
    try:
        while True:
            data = await websocket.receive()
            
            if "bytes" in data:
                # Handle binary audio data
                audio_bytes = data["bytes"]
                
                # Store in Redis with a timestamp key
                timestamp = time.time()
                audio_key = f"audio:{session_id}:{timestamp}"
                redis_conn.set(audio_key, audio_bytes, ex=300)
                
                # Add this chunk to the user's dedicated queue
                job = user_queue.enqueue(
                    'app.audio_processor.process_user_audio_chunk',
                    session_id=session_id,
                    audio_key=audio_key,
                    timestamp=timestamp
                )
                
                # Save the last job ID for dependencies if needed
                redis_conn.set(f"last_job:{session_id}", job.id, ex=300)
                
                # Send acknowledgment
                await websocket.send_text(json.dumps({
                    "type": "ack", 
                    "message": f"Received {len(audio_bytes)} bytes"
                }))
                
            elif "text" in data:
                try:
                    message = json.loads(data["text"])
                    logger.info(f"Received message: {message}")
                    
                    command_type = message.get("type")
                    
                    if command_type == "end_stream":
                        # Signal end of audio stream
                        await asyncio.to_thread(
                            session_queue.enqueue,
                            'app.audio_processor.end_stream_processing',
                            session_id=session_id,
                            device_id=device_id
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
        logger.info(f"ESP device disconnected: {device_id}, session: {session_id}")
        # Clean up
        if session_id in active_connections:
            del active_connections[session_id]
        
        # Signal stream end when client disconnects
        try:
            await asyncio.to_thread(
                session_queue.enqueue,
                'app.audio_processor.end_stream_processing',
                session_id=session_id,
                device_id=device_id,
                reason="disconnect"
            )
        except Exception as e:
            logger.error(f"Error signaling stream end on disconnect: {e}")
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        # Clean up
        if session_id in active_connections:
            del active_connections[session_id]

@app.on_event("startup")
async def start_workers():
    """Start the audio worker processes"""
    asyncio.create_task(start_audio_worker())