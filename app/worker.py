# app/worker.py
import asyncio
import json
import logging
import time
import uuid
import httpx
from app.redis_client import get_redis_client, get_redis_pubsub
from app.audio_processor import AudioProcessor, text_to_speech
from app.config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

async def start_audio_worker():
    """Start the audio processing worker"""
    logger.info("Starting audio processing worker")
    workflow_engines = {}
    redis = await get_redis_client()
    pubsub = await get_redis_pubsub()
    
    # Subscribe to audio processing channel
    await pubsub.subscribe("audio:processing")
    
    # Create audio processor
    processor = AudioProcessor()
    
    # Process messages forever
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    session_id = data.get("session_id")
                    audio_key = data.get("audio_key")
                    user_id = data.get("user_id")

                    if user_id not in workflow_engines:
                        # Get user data from Redis
                        user_data_bytes = await redis.get(f"user:{user_id}")
                        if user_data_bytes:
                            user_data = json.loads(user_data_bytes)
                        else:
                            # Get from Firebase if needed
                            from app.firebase_service import get_user_from_firestore
                            user_data = await get_user_from_firestore(user_id)
                            if user_data:
                                # Cache in Redis
                                await redis.set(
                                    f"user:{user_id}", 
                                    json.dumps(user_data),
                                    ex=3600
                                )
                        
                        # Create workflow engine
                        workflow_engines[user_id] = WorkflowEngine(user_id, user_data)
                    
                    workflow = workflow_engines[user_id]
                    
                    # Get audio data from Redis
                    audio_data = await redis.get(audio_key)
                    if not audio_data:
                        logger.warning(f"Audio data not found: {audio_key}")
                        continue
                    
                    # Process audio
                    processor.add_audio(audio_data)
                    
                    if processor.buffer_ready_for_processing():
                        # Get transcription
                        transcription = await processor.process_buffer()
                        
                        if transcription:
                            # Publish transcription
                            await redis.publish(
                                f"responses:{session_id}",
                                json.dumps({
                                    "type": "transcription",
                                    "text": transcription
                                })
                            )
                            
                            # Generate a dummy response for now
                            response_text = f"Echo: {transcription}"
                            
                            # Publish response text
                            await redis.publish(
                                f"responses:{session_id}",
                                json.dumps({
                                    "type": "response_chunk",
                                    "text": response_text
                                })
                            )
                            
                            # Generate audio for the response
                            audio_response = await text_to_speech(response_text)
                            
                            if audio_response:
                                # Store in Redis
                                response_key = f"response:{session_id}:{uuid.uuid4()}"
                                await redis.set(response_key, audio_response, ex=60)
                                
                                # Publish notification
                                await redis.publish(
                                    f"responses:{session_id}",
                                    json.dumps({
                                        "type": "audio_response",
                                        "audio_key": response_key
                                    })
                                )
                                response_text = await workflow.process_transcription(transcription)
                
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
    
    except asyncio.CancelledError:
        await pubsub.unsubscribe()
        logger.info("Worker stopped")
    
    except Exception as e:
        logger.error(f"Worker error: {e}")

# Add to main.py to start worker
@app.on_event("startup")
async def start_workers():
    asyncio.create_task(start_audio_worker())