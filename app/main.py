import time
import wave
from io import BytesIO
from pydub import AudioSegment
import asyncio
import logging
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.redis.redis_client import get_redis_client, get_redis_pubsub
from app.redis.worker import start_audio_worker
from app.config import FIREBASE_CREDENTIALS_PATH, SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH
from redis import Redis
from rq import Queue
from app.firebase_service import initialize_firebase, get_user_from_firestore
from app.syllabus_manager import SyllabusManager
from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException

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
    
    # Create PubSub subscription for agent responses
    pubsub = redis_conn.pubsub()
    pubsub.subscribe(f"agent:updates:{session_id}")
    
    # Start background task to listen for agent responses
    background_tasks = BackgroundTasks()
    background_tasks.add_task(listen_for_agent_responses, pubsub, websocket, session_id)
    
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
                        
                    elif command_type == "text_input":
                        # Handle direct text input (for testing/fallback)
                        text_content = message.get("content", "")
                        if text_content:
                            # Create a key to store the text
                            text_key = f"text:{session_id}:{time.time()}"
                            redis_conn.set(text_key, text_content, ex=300)
                            
                            # Process directly with agent (skip audio processing)
                            agent_queue = Queue('agent_processing', connection=redis_conn)
                            agent_job = agent_queue.enqueue(
                                'app.agent_worker.process_text_input',
                                session_id=session_id,
                                text_key=text_key,
                                job_id=f"text_input_{session_id}_{time.time()}"
                            )
                            
                            await websocket.send_text(json.dumps({
                                "type": "info",
                                "message": "Text input received and being processed"
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

# Add this function for agent response handling
async def listen_for_agent_responses(pubsub, websocket, session_id):
    """Listen for agent responses from Redis PubSub"""
    try:
        logger.info(f"Starting agent response listener for session {session_id}")
        # Process any messages already in the queue
        for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    # Parse message data
                    data = json.loads(message['data'])
                    message_type = data.get('type')
                    
                    if message_type == 'response':
                        # Send response to client
                        response = data.get('data', {})
                        text_response = response.get('response', '')
                        
                        if text_response:
                            await websocket.send_text(json.dumps({
                                "type": "agent_response",
                                "message": text_response
                            }))
                    
                    elif message_type == 'session_ended':
                        # Notify client that session has ended
                        await websocket.send_text(json.dumps({
                            "type": "session_ended",
                            "message": "Session has ended"
                        }))
                        break
                
                except json.JSONDecodeError:
                    logger.error("Invalid JSON in Redis message")
                except Exception as e:
                    logger.error(f"Error processing Redis message: {e}")
    
    except Exception as e:
        logger.error(f"Error in agent response listener: {e}")
    finally:
        # Clean up
        pubsub.unsubscribe()
        logger.info(f"Agent response listener for session {session_id} stopped")

@app.get("/agent/user/{user_id}")
async def get_user_data(user_id: str):
    """Get user data from Firestore"""
    user_data = get_user_from_firestore(user_id)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    return user_data

@app.get("/agent/games")
async def get_available_games():
    """Get list of available language games"""
    syllabus = SyllabusManager()
    await syllabus.initialize()
    games = syllabus.get_all_games()
    return games


@app.on_event("startup")
async def startup_event():
    """Initialize application components on startup"""
    # Initialize Firebase
    initialize_firebase()
    
    # Initialize Syllabus Manager
    syllabus = SyllabusManager()
    await syllabus.initialize()
    
    # Start the audio worker processes
    asyncio.create_task(start_audio_worker())