# app/workflow_engine.py
import json
import logging
import asyncio
from app.redis.redis_client import get_redis_client
# from app.openai_service import transcribe_audio, generate_speech

logger = logging.getLogger(__name__)

class WorkflowEngine:
    """Basic workflow engine for language tutorial"""
    
    def __init__(self, user_id, user_data=None):
        self.user_id = user_id
        self.user_data = user_data or {}
        self.context = {
            "child_name": self.user_data.get("name"),
            "child_age": self.user_data.get("age"),
            "learned_words": {},
            "current_game": None
        }
        self.last_response = None
    
    async def process_transcription(self, transcription):
        """Process user transcription and generate response"""
        try:
            redis = await get_redis_client()
            
            # Store transcription in history
            history_key = f"conversation:{self.user_id}"
            await redis.rpush(
                history_key,
                json.dumps({"role": "user", "content": transcription})
            )
            await redis.ltrim(history_key, -10, -1)  # Keep last 10 messages
            
            # For now, generate a simple response
            # In a real implementation, this would use OpenAI API
            if "hello" in transcription.lower():
                response = f"¡Hola {self.context['child_name'] or 'amigo'}! How are you today?"
            elif "animal" in transcription.lower():
                response = "Let's learn about animals! In Spanish, 'dog' is 'perro'. Can you say 'perro'?"
                # Track this word
                await self.track_vocabulary("perro", "dog", "animal lesson")
            else:
                response = f"I heard you say: {transcription}. What would you like to learn today?"
            
            # Store response in history
            await redis.rpush(
                history_key,
                json.dumps({"role": "assistant", "content": response})
            )
            
            self.last_response = response
            return response
            
        except Exception as e:
            logger.error(f"Error in workflow: {e}")
            return "I'm sorry, I had a problem. Could you try again?"
    
    async def track_vocabulary(self, word, translation, context):
        """Track vocabulary word"""
        try:
            redis = await get_redis_client()
            
            # Store in user's vocabulary
            vocab_key = f"vocabulary:{self.user_id}"
            await redis.hset(
                vocab_key,
                word,
                json.dumps({
                    "translation": translation,
                    "context": context,
                    "timestamp": asyncio.get_event_loop().time()
                })
            )
            
            # Update context
            self.context["learned_words"][word] = translation
            
            # Mark user data as modified
            await redis.set(f"user:{self.user_id}:modified", "1", ex=3600)
            
            return True
        except Exception as e:
            logger.error(f"Error tracking vocabulary: {e}")
            return False