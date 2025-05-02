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

async def process_audio_keys():
    """Listen for audio keys on the PubSub channel and process them"""
    redis_client = await get_redis_client()
    pubsub = redis_client.pubsub()
    
    # Subscribe to the audio:keys channel
    await pubsub.subscribe("audio:keys")
    logger.info("Subscribed to audio:keys channel")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    # Parse the message data
                    data = json.loads(message["data"])
                    session_id = data.get("session_id")
                    device_id = data.get("device_id")
                    audio_key = data.get("audio_key")
                    
                    logger.info(f"Received audio key: {audio_key} from device: {device_id}")
                    
                    # Retrieve the audio data from Redis
                    audio_data = await redis_client.get(audio_key)
                    
                    if audio_data:
                        # Log that we received the audio data
                        logger.info(f"Retrieved audio data: {len(audio_data)} bytes")
                        
                        # Here you would typically process the audio data
                        # For this example, we're just logging that we received it
                        logger.info(f"Audio data from {device_id} successfully retrieved")
                        
                        # You could also delete the audio data from Redis if no longer needed
                        # await redis_client.delete(audio_key)
                    else:
                        logger.warning(f"Audio data not found for key: {audio_key}")
                    
                except json.JSONDecodeError:
                    logger.error("Invalid JSON in message data")
                except Exception as e:
                    logger.error(f"Error processing audio key: {e}")
    
    except asyncio.CancelledError:
        logger.info("Consumer task cancelled")
        await pubsub.unsubscribe()
        await redis_client.close()
    
    except Exception as e:
        logger.error(f"Unexpected error in consumer: {e}")
        await pubsub.unsubscribe()
        await redis_client.close()

async def process_audio_control():
    """Listen for control messages on the PubSub channel"""
    redis_client = await get_redis_client()
    pubsub = redis_client.pubsub()
    
    # Subscribe to the audio:control channel
    await pubsub.subscribe("audio:control")
    logger.info("Subscribed to audio:control channel")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    # Parse the message data
                    data = json.loads(message["data"])
                    session_id = data.get("session_id")
                    device_id = data.get("device_id")
                    command = data.get("command")
                    
                    logger.info(f"Received control command: {command} from device: {device_id}")
                    
                    # Process different commands
                    if command == "end_stream":
                        logger.info(f"End of stream from device: {device_id}")
                        # Here you might want to trigger processing of the complete audio
                        
                except json.JSONDecodeError:
                    logger.error("Invalid JSON in message data")
                except Exception as e:
                    logger.error(f"Error processing control message: {e}")
    
    except asyncio.CancelledError:
        logger.info("Control listener task cancelled")
        await pubsub.unsubscribe()
        await redis_client.close()
    
    except Exception as e:
        logger.error(f"Unexpected error in control listener: {e}")
        await pubsub.unsubscribe()
        await redis_client.close()

async def main():
    """Run all consumer tasks"""
    # Create tasks for each listener
    audio_keys_task = asyncio.create_task(process_audio_keys())
    audio_control_task = asyncio.create_task(process_audio_control())
    
    # Wait for both tasks to complete
    try:
        await asyncio.gather(audio_keys_task, audio_control_task)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        audio_keys_task.cancel()
        audio_control_task.cancel()
        await asyncio.gather(audio_keys_task, audio_control_task, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())