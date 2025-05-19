# app/spanish_workflow.py

import logging
import json
import re
import time
import asyncio
from typing import Dict, List, Optional, AsyncGenerator, Any, Callable
import firebase_admin
from firebase_admin import credentials, firestore

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

class LanguageTutorContext:
    """Context for tracking state in the language tutor workflow"""
    def __init__(self):
        self.child_age = None
        self.child_name = None
        self.learned_words = {}  # Spanish word -> English translation
        self.current_game = None
        self.engagement_score = 3  # Start with neutral engagement

# Default user template matching the one from my_workflow.py
DEFAULT_USER_TEMPLATE = {
    'id': None,
    'name': None,
    'age': None,
    'language': 'Spanish',
    'proficiency': 'Beginner',
    'vocabulary': {},
    'session_history': []
}

class SpanishWorkflow:
    """
    Adapts the MyWorkflow functionality to the server architecture.
    This provides Spanish language tutoring through different agents.
    """
    def __init__(self, session_id: str, device_id: str, user_id: Optional[str] = None):
        """
        Initialize the Spanish language tutor workflow.
        
        Args:
            session_id: Unique session identifier
            device_id: Device identifier
            user_id: Optional user ID (defaults to device_id)
        """
        self.session_id = session_id
        self.device_id = device_id
        self.user_id = user_id or device_id
        
        # Internal state
        self.current_agent = "UserInfoCollector"  # Default agent
        self.message_history = []
        self.context = LanguageTutorContext()
        
        # User data
        self.user_data = DEFAULT_USER_TEMPLATE.copy()
        self.user_data['id'] = self.user_id
        
        logger.info(f"Created Spanish workflow for session {session_id}, user {self.user_id}")
    
    async def initialize(self):
        """Initialize the workflow and load user data"""
        # Load user data if available
        from app.firebase_service import get_user_from_firestore
        
        user_data = get_user_from_firestore(self.user_id)
        if user_data:
            # Update user context with loaded data
            for key, value in user_data.items():
                if value is not None and key in self.user_data:
                    self.user_data[key] = value
            logger.info(f"Loaded user data for {self.user_id}")
            
            # Update context with user data
            self.context.child_name = self.user_data.get('name')
            self.context.child_age = self.user_data.get('age')
            
            # Add any existing vocabulary
            if 'vocabulary' in user_data and isinstance(user_data['vocabulary'], dict):
                for word, word_info in user_data['vocabulary'].items():
                    if isinstance(word_info, dict) and 'translation' in word_info:
                        self.context.learned_words[word] = word_info['translation']
        
        # Determine initial agent based on user data
        if self.user_data.get('name') is None or self.user_data.get('age') is None:
            # Missing user info, start with UserInfoCollector
            self.current_agent = "UserInfoCollector"
            greeting = "¡Hola! I'm your Spanish language tutor. Before we start, could you tell me your name and how old you are?"
        else:
            # User info complete, start with ChoiceLayer
            self.current_agent = "ChoiceLayer"
            name = self.user_data.get('name')
            greeting = f"¡Hola {name}! I'm your Spanish language tutor. What would you like to learn today?"
        
        # Add initial greeting to message history
        self.message_history.append({
            "role": "assistant",
            "content": greeting
        })
        
        return True
    
    async def process_transcription(self, transcription: str) -> AsyncGenerator[str, None]:
        """
        Process user transcription and generate agent response
        
        Args:
            transcription: Text transcription from audio
            
        Yields:
            Response chunks from the agent
        """
        logger.info(f"Processing transcription for session {self.session_id}: {transcription[:50]}...")
        
        # Add user message to history
        self.message_history.append({
            "role": "user",
            "content": transcription
        })
        
        # Trim history if needed
        if len(self.message_history) > 20:
            # Keep first assistant message and last 19 messages
            self.message_history = [self.message_history[0]] + self.message_history[-19:]
        
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
            self.context.current_game = game_switch["id"]
        
        # Get appropriate prompt for the current agent
        prompt = await self._get_agent_prompt()
        
        # Format messages with prompt
        formatted_messages = self._format_messages_with_prompt(prompt)
        
        try:
            # Load appropriate tools based on the current agent
            tools = self._get_tools_for_agent()
            
            # Generate response
            from app.openai_service import generate_streaming_response, generate_response
            
            # Generate streaming response
            async for chunk in generate_streaming_response(
                messages=formatted_messages,
                tools=tools,
                model="gpt-4o"
            ):
                yield chunk
                
            # Get the full response (for history and tool calls)
            response = await generate_response(
                messages=formatted_messages,
                tools=tools,
                model="gpt-4o"
            )
            
            # Process tool calls if any
            tool_calls = self._extract_tool_calls(response)
            if tool_calls:
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
                    self.context.current_game = None
                # If we've collected user info, update fields
                if self.current_agent == "ChoiceLayer" and self.user_data.get('name') is not None:
                    logger.info(f"Agent handoff to ChoiceLayer with updated user info")
            
            # Store session state for persistence
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
    
    def _store_session_state(self):
        """Store session state for persistence"""
        # This would store the state in Redis or another persistence store
        # For now we'll implement a placeholder
        logger.info(f"Storing session state for {self.session_id}")
        # In a real implementation, this would be stored in Redis or a database
    
    def _check_game_switch(self, transcription: str) -> Optional[Dict]:
        """Check for direct game switching commands"""
        from app.syllabus_manager import SyllabusManager
        
        lowercase_input = transcription.lower()
        
        # Get available games from syllabus manager
        syllabus = SyllabusManager()
        available_games = syllabus.get_all_games()
        
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
    
    async def _get_agent_prompt(self) -> str:
        """Get the appropriate prompt for the current agent"""
        from app.syllabus_manager import SyllabusManager
        
        syllabus = SyllabusManager()
        await syllabus.initialize()
        
        if self.current_agent == "UserInfoCollector":
            prompt = syllabus.get_prompt("USER_INFO_PROMPT")
        elif self.current_agent == "ChoiceLayer":
            prompt = syllabus.get_prompt("CHOICE_LAYER_PROMPT")
            
            # Add available games info to the choice layer prompt
            games = syllabus.get_all_games()
            games_info = "\n\nAVAILABLE_GAMES:\n"
            for game_id, game in games.items():
                games_info += f"- {game_id}: {game['name']} - {game['description']}\n"
            
            prompt += games_info
        else:
            # This is a game prompt
            prompt = syllabus.get_game_prompt(self.current_agent)
        
        # Replace user templates
        prompt = syllabus.replace_user_templates(prompt, self.user_data)
        
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
                from app.firebase_service import add_user_to_firestore
                
                name = arguments.get("name")
                age = arguments.get("age")
                
                if name and age:
                    # Update user data
                    self.user_data["name"] = name
                    self.user_data["age"] = age
                    
                    # Update context
                    self.context.child_name = name
                    self.context.child_age = age
                    
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
                from app.firebase_service import add_user_to_firestore
                
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
                    
                    # Update context
                    self.context.learned_words[word] = translation
                    
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
            from app.syllabus_manager import SyllabusManager
            
            syllabus = SyllabusManager()
            games = syllabus.get_all_games()
            
            for game_id, game_info in games.items():
                game_name = game_info["name"].lower()
                
                # Look for game selection indicators
                if ((f"welcome to {game_name}" in content_lower or
                     f"let's play {game_name}" in content_lower or
                     f"starting {game_name}" in content_lower) and
                    "get ready" in content_lower):
                    return game_id
        
        elif self.current_agent != "ChoiceLayer" and self.context.current_game:
            # Check if returning to ChoiceLayer from a game
            if ("back to the main menu" in content_lower or
                "what would you like to play next" in content_lower or
                "choose another game" in content_lower):
                return "ChoiceLayer"
        
        return None
    
    @classmethod
    async def load_or_create(cls, session_id: str, device_id: str, user_id: Optional[str] = None) -> 'SpanishWorkflow':
        """Load an existing workflow session or create a new one"""
        # In a real implementation, this would load from Redis
        # For now, we'll just create a new one
        workflow = cls(session_id, device_id, user_id)
        await workflow.initialize()
        return workflow