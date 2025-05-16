# app/agent_worker.py
import logging
import json
import time
import asyncio
from typing import Dict, List, Optional, AsyncGenerator, Any
import redis
from rq import Queue

from app.syllabus_manager import SyllabusManager
from app.firebase_service import get_user_from_firestore, add_user_to_firestore
from app.openai_service import (
    transcribe_audio, 
    generate_response, 
    generate_streaming_response,
    generate_speech
)

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Redis connection
redis_conn = redis.Redis(host='localhost', port=6379, db=0)

# Default user template
DEFAULT_USER_TEMPLATE = {
    'id': None,
    'name': None,
    'age': None,
    'language': 'Spanish',
    'proficiency': 'Beginner',
    'vocabulary': {},
    'session_history': []
}

class AgentSession:
    """
    Manages a conversation session with an agent for a user
    """
    def __init__(
        self, 
        session_id: str, 
        device_id: str, 
        user_id: Optional[str] = None
    ):
        self.session_id = session_id
        self.device_id = device_id
        self.user_id = user_id or device_id
        self.active = True
        self.start_time = time.time()
        self.last_activity = time.time()
        
        # Conversation state
        self.current_agent = "UserInfoCollector"  # Default to user info collection
        self.current_game = None
        self.message_history = []
        self.conversation_context = {}
        
        # User data
        self.user_data = DEFAULT_USER_TEMPLATE.copy()
        self.user_data['id'] = self.user_id
        
        # Syllabus manager
        self.syllabus = SyllabusManager()
        
        logger.info(f"Created agent session {session_id} for device {device_id}, user {self.user_id}")
    
    async def initialize(self):
        """Initialize the session and load user data"""
        # Initialize the syllabus manager
        syllabus_initialized = await self.syllabus.initialize()
        if not syllabus_initialized:
            logger.error(f"Failed to initialize syllabus for session {self.session_id}")
            return False
        
        # Load user data if available
        user_data = get_user_from_firestore(self.user_id)
        if user_data:
            # Update user context with loaded data
            for key, value in user_data.items():
                if value is not None:
                    self.user_data[key] = value
            logger.info(f"Loaded user data for {self.user_id}")
        
        # Add initial greeting based on user data
        if self.user_data.get('name'):
            greeting = f"¡Hola {self.user_data['name']}! I'm your Spanish language tutor. What would you like to learn today?"
            self.current_agent = "ChoiceLayer"  # Skip to choice layer if we know the user
        else:
            greeting = "¡Hola! I'm your Spanish language tutor. Before we start, could you tell me your name and how old you are?"
            self.current_agent = "UserInfoCollector"
        
        # Add greeting to history
        self.message_history.append({
            "role": "assistant",
            "content": greeting
        })
        
        # Store session in Redis for persistence
        self._store_session_state()
        
        return True
    
    def _store_session_state(self):
        """Store session state in Redis"""
        # Create a serializable state object
        state = {
            "session_id": self.session_id,
            "device_id": self.device_id,
            "user_id": self.user_id,
            "active": self.active,
            "start_time": self.start_time,
            "last_activity": self.last_activity,
            "current_agent": self.current_agent,
            "current_game": self.current_game,
            "message_history": self.message_history,
            "conversation_context": self.conversation_context,
            "user_data": self.user_data
        }
        
        # Store in Redis with 1 hour expiration
        redis_conn.set(
            f"agent_session:{self.session_id}", 
            json.dumps(state),
            ex=3600  # 1 hour expiration
        )
    
    @classmethod
    def load_from_redis(cls, session_id: str) -> Optional['AgentSession']:
        """Load session from Redis"""
        session_data = redis_conn.get(f"agent_session:{session_id}")
        if not session_data:
            logger.warning(f"Session {session_id} not found in Redis")
            return None
        
        try:
            state = json.loads(session_data)
            
            # Create new session object
            session = cls(
                session_id=state["session_id"],
                device_id=state["device_id"],
                user_id=state["user_id"]
            )
            
            # Restore state
            session.active = state["active"]
            session.start_time = state["start_time"]
            session.last_activity = state["last_activity"]
            session.current_agent = state["current_agent"]
            session.current_game = state["current_game"]
            session.message_history = state["message_history"]
            session.conversation_context = state["conversation_context"]
            session.user_data = state["user_data"]
            
            # Initialize syllabus
            asyncio.create_task(session.syllabus.initialize())
            
            return session
        except Exception as e:
            logger.error(f"Error loading session {session_id}: {e}")
            return None
    
    async def process_transcription(self, transcription: str) -> AsyncGenerator[str, None]:
        """
        Process user transcription and generate agent response
        
        Args:
            transcription: Text transcription from audio
            
        Yields:
            Response chunks from the agent
        """
        logger.info(f"Processing transcription for session {self.session_id}: {transcription[:50]}...")
        
        # Update activity timestamp
        self.last_activity = time.time()
        
        # Add user message to history
        self.message_history.append({
            "role": "user",
            "content": transcription
        })
        
        # Trim history if needed
        if len(self.message_history) > 20:
            self.message_history = self.message_history[-20:]
        
        # Prepare tools based on current agent
        tools = self._get_tools_for_agent()
        
        # Check for direct game switching
        game_switch = self._check_game_switch(transcription)
        if game_switch:
            # Yield the switch message
            switch_message = f"Switching to {game_switch['name']}! Get ready for a fun adventure!"
            yield switch_message
            
            # Add to history
            self.message_history.append({
                "role": "assistant",
                "content": switch_message
            })
            
            # Update agent and game
            self.current_agent = game_switch["id"]
            self.current_game = game_switch["id"]
            
            # Update tools
            tools = self._get_tools_for_agent()
        
        # Get appropriate prompt for the current agent
        prompt = self._get_agent_prompt()
        
        # Format messages with prompt
        formatted_messages = self._format_messages_with_prompt(prompt)
        
        try:
            # Generate streaming response
            async for chunk in generate_streaming_response(
                messages=formatted_messages,
                tools=tools,
                model="gpt-4o"  # Use OpenAI's best model
            ):
                yield chunk
                
            # Get the full response (for history)
            response = await generate_response(
                messages=formatted_messages,
                tools=tools,
                model="gpt-4o"
            )
            
            # Process tool calls if any
            tool_calls = self._extract_tool_calls(response)
            if tool_calls:
                # Execute each tool call
                for tool_call in tool_calls:
                    tool_result = await self._execute_tool_call(tool_call)
                    
                    # If there's a visible result to show the user
                    if tool_result.get("visible_result"):
                        yield tool_result["visible_result"]
            
            # Extract the full response content
            content = self._extract_response_content(response)
            
            # Add assistant response to history
            self.message_history.append({
                "role": "assistant",
                "content": content
            })
            
            # Check for agent handoff in response
            handoff = self._check_for_handoff(content)
            if handoff:
                self.current_agent = handoff
                # If switching to ChoiceLayer, clear current game
                if handoff == "ChoiceLayer":
                    self.current_game = None
            
            # Save session state
            self._store_session_state()
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            error_message = "I'm sorry, I had a problem understanding. Could you try again?"
            yield error_message
            
            self.message_history.append({
                "role": "assistant",
                "content": error_message
            })
            self._store_session_state()
    
    def _check_game_switch(self, transcription: str) -> Optional[Dict]:
        """Check for direct game switching commands"""
        lowercase_input = transcription.lower()
        
        available_games = self.syllabus.get_all_games()
        
        for game_id, game_info in available_games.items():
            game_name = game_info["name"].lower()
            
            # Check for common patterns to switch games
            if (f"play {game_id.lower()}" in lowercase_input or 
                f"play {game_name}" in lowercase_input or
                f"switch to {game_name}" in lowercase_input or
                game_name in lowercase_input):
                
                logger.info(f"Detected request to switch to game {game_id}")
                return game_info
        
        return None
    
    def _get_agent_prompt(self) -> str:
        """Get the appropriate prompt for the current agent"""
        if self.current_agent == "UserInfoCollector":
            prompt = self.syllabus.get_prompt("USER_INFO_PROMPT")
        elif self.current_agent == "ChoiceLayer":
            prompt = self.syllabus.get_prompt("CHOICE_LAYER_PROMPT")
            
            # Add available games info to the choice layer prompt
            games = self.syllabus.get_all_games()
            games_info = "\n\nAVAILABLE_GAMES:\n"
            for game_id, game in games.items():
                games_info += f"- {game_id}: {game['name']} - {game['description']}\n"
            
            prompt += games_info
        else:
            # This is a game prompt
            prompt = self.syllabus.get_game_prompt(self.current_agent)
        
        # Replace user templates
        prompt = self.syllabus.replace_user_templates(prompt, self.user_data)
        
        return prompt
    
    def _format_messages_with_prompt(self, prompt: str) -> List[Dict]:
        """Format conversation history with system prompt"""
        formatted_messages = [
            {
                "role": "system",
                "content": prompt
            }
        ]
        
        # Add conversation history
        formatted_messages.extend(self.message_history)
        
        return formatted_messages
    
    def _get_tools_for_agent(self) -> List[Dict]:
        """Get the appropriate tools for the current agent"""
        # Common tool definitions
        save_user_info_tool = {
            "type": "function",
            "function": {
                "name": "save_user_info",
                "description": "Save the user's basic information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The user's name"
                        },
                        "age": {
                            "type": "integer",
                            "description": "The user's age"
                        }
                    },
                    "required": ["name", "age"]
                }
            }
        }
        
        track_vocabulary_tool = {
            "type": "function",
            "function": {
                "name": "track_vocabulary",
                "description": "Track a Spanish vocabulary word that was taught to the child",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "word": {
                            "type": "string",
                            "description": "The Spanish vocabulary word being tracked"
                        },
                        "translation": {
                            "type": "string",
                            "description": "The English translation of the word"
                        },
                        "context": {
                            "type": "string",
                            "description": "Additional context about how the word was taught"
                        }
                    },
                    "required": ["word", "translation"]
                }
            }
        }
        
        get_child_name_tool = {
            "type": "function",
            "function": {
                "name": "get_child_name",
                "description": "Get the child's name from the system",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
        
        get_child_age_tool = {
            "type": "function",
            "function": {
                "name": "get_child_age",
                "description": "Get the child's age from the system",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
        
        # Return tools based on current agent
        if self.current_agent == "UserInfoCollector":
            return [save_user_info_tool, get_child_name_tool, get_child_age_tool]
        elif self.current_agent == "ChoiceLayer":
            return [track_vocabulary_tool, get_child_name_tool, get_child_age_tool]
        else:
            # Game agent
            return [track_vocabulary_tool, get_child_name_tool, get_child_age_tool]
    
    def _extract_tool_calls(self, response: Dict) -> List[Dict]:
        """Extract tool calls from the response"""
        try:
            # Check if there are any tool calls in the response
            choices = response.get("choices", [])
            if not choices:
                return []
                
            message = choices[0].get("message", {})
            tool_calls = message.get("tool_calls", [])
            
            # Format tool calls for processing
            formatted_calls = []
            for call in tool_calls:
                try:
                    function = call.get("function", {})
                    formatted_calls.append({
                        "id": call.get("id", ""),
                        "name": function.get("name", ""),
                        "arguments": json.loads(function.get("arguments", "{}"))
                    })
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON in tool call arguments: {function.get('arguments')}")
            
            return formatted_calls
        except Exception as e:
            logger.error(f"Error extracting tool calls: {e}")
            return []
    
    async def _execute_tool_call(self, tool_call: Dict) -> Dict:
        """Execute a tool call and return the result"""
        function_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})
        
        logger.info(f"Executing tool call: {function_name} with args: {arguments}")
        
        result = {
            "success": False,
            "result": None,
            "visible_result": None
        }
        
        try:
            if function_name == "save_user_info":
                name = arguments.get("name")
                age = arguments.get("age")
                
                if name and age:
                    # Update user data
                    self.user_data["name"] = name
                    self.user_data["age"] = age
                    
                    # Save to Firebase
                    success = add_user_to_firestore(
                        user_id=self.user_id,
                        name=name,
                        age=age,
                        language=self.user_data.get("language", "Spanish"),
                        proficiency=self.user_data.get("proficiency", "Beginner")
                    )
                    
                    result = {
                        "success": success,
                        "result": f"Saved user info: {name}, age {age}",
                        "visible_result": None  # Don't show this to the user
                    }
            
            elif function_name == "track_vocabulary":
                word = arguments.get("word")
                translation = arguments.get("translation")
                context = arguments.get("context", "")
                
                if word and translation:
                    # Track vocabulary word
                    vocabulary = self.user_data.get("vocabulary", {})
                    vocabulary[word] = {
                        "translation": translation,
                        "context": context,
                        "timestamp": time.time()
                    }
                    
                    # Update user data
                    self.user_data["vocabulary"] = vocabulary
                    
                    # Save to Firebase
                    success = add_user_to_firestore(
                        user_id=self.user_id,
                        vocabulary=vocabulary
                    )
                    
                    result = {
                        "success": success,
                        "result": f"Added '{word}' ({translation}) to vocabulary",
                        "visible_result": None  # Don't show this to the user
                    }
            
            elif function_name == "get_child_name":
                result = {
                    "success": True,
                    "result": self.user_data.get("name"),
                    "visible_result": None
                }
            
            elif function_name == "get_child_age":
                result = {
                    "success": True,
                    "result": self.user_data.get("age"),
                    "visible_result": None
                }
            
            else:
                logger.warning(f"Unknown function: {function_name}")
                result = {
                    "success": False,
                    "result": f"Unknown function: {function_name}",
                    "visible_result": None
                }
        
        except Exception as e:
            logger.error(f"Error executing tool call {function_name}: {e}")
            result = {
                "success": False,
                "result": f"Error: {str(e)}",
                "visible_result": None
            }
        
        return result
    
    def _extract_response_content(self, response: Dict) -> str:
        """Extract text content from response"""
        try:
            choices = response.get("choices", [])
            if not choices:
                return ""
                
            message = choices[0].get("message", {})
            return message.get("content", "")
        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            return ""
    
    def _check_for_handoff(self, content: str) -> Optional[str]:
        """Check if response indicates agent handoff"""
        # Simple detection based on keywords
        content_lower = content.lower()
        
        if self.current_agent == "UserInfoCollector":
            # Check if user info has been collected, switch to ChoiceLayer
            if (self.user_data.get("name") and self.user_data.get("age") and
                ("what would you like to learn" in content_lower or
                 "what would you like to play" in content_lower or
                 "choose a game" in content_lower)):
                return "ChoiceLayer"
        
        elif self.current_agent == "ChoiceLayer":
            # Check if a game has been selected
            games = self.syllabus.get_all_games()
            
            for game_id, game_info in games.items():
                game_name = game_info["name"].lower()
                
                # Look for game selection indicators
                if ((f"welcome to {game_name}" in content_lower or
                     f"let's play {game_name}" in content_lower or
                     f"starting {game_name}" in content_lower) and
                    "get ready" in content_lower):
                    return game_id
        
        elif self.current_agent != "ChoiceLayer" and self.current_game:
            # Check if returning to ChoiceLayer from a game
            if ("back to the main menu" in content_lower or
                "what would you like to play next" in content_lower or
                "choose another game" in content_lower):
                return "ChoiceLayer"
        
        return None

# Job functions for Redis queue
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
        
        # Convert to proper audio format if needed
        # This would be done in a real implementation
        
        # Transcribe audio using OpenAI Whisper
        transcription = loop.run_until_complete(transcribe_audio(audio_data))
        
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
        
        # Generate speech from response
        # In a real implementation, this would convert the response to audio
        # speech_data = loop.run_until_complete(generate_speech(response_text))
        
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