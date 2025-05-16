# app/syllabus_manager.py
import logging
import json
import re
from typing import Dict, List, Optional, Any
from app.firebase_service import get_all_prompts

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

class SyllabusManager:
    """Manager for educational content and prompts"""
    
    def __init__(self):
        self.prompts = {}
        self.games = {}
        self.user_templates = {}
    
    async def initialize(self):
        """Load all prompts and initialize the syllabus"""
        self.prompts = get_all_prompts()
        if not self.prompts:
            logger.error("Failed to load prompts from Firebase")
            return False
            
        # Detect and categorize game prompts
        self._detect_game_prompts()
        
        # Verify essential prompts are present
        if not self._verify_essential_prompts():
            logger.error("Essential prompts are missing")
            return False
            
        logger.info(f"Syllabus initialized with {len(self.prompts)} prompts and {len(self.games)} games")
        return True
    
    def _verify_essential_prompts(self) -> bool:
        """Verify that all essential prompts are present"""
        essential_prompts = [
            "USER_INFO_PROMPT", 
            "CHOICE_LAYER_PROMPT"
        ]
        
        missing = [prompt for prompt in essential_prompts if prompt not in self.prompts]
        
        if missing:
            logger.error(f"Missing essential prompts: {', '.join(missing)}")
            return False
            
        # Ensure we have at least one game prompt
        if not self.games:
            logger.error("No game prompts detected")
            return False
            
        return True
    
    def _detect_game_prompts(self):
        """Detect game prompts and extract metadata"""
        game_pattern = re.compile(r'(.+)_GAME_PROMPT$')
        
        for prompt_id, content in self.prompts.items():
            match = game_pattern.match(prompt_id)
            
            if match:
                game_id = match.group(1)  # Extract the game name
                
                # Extract game name from content (first line often has it)
                name = game_id.replace("_", " ")  # Default name
                description = f"Learn Spanish through a fun {game_id.lower()} game!"
                
                # Try to extract better name/description from prompt content
                if "game is called" in content.lower():
                    # Look for line with "game is called"
                    for line in content.split('\n'):
                        if "game is called" in line.lower():
                            # Extract text within quotes if present
                            name_match = re.search(r'"([^"]+)"', line)
                            if name_match:
                                name = name_match.group(1)
                            else:
                                # Try extracting text after "called"
                                name_match = re.search(r'called\s+(.+?)[\.\s]', line)
                                if name_match:
                                    name = name_match.group(1).strip('" ')
                
                # Store game metadata
                self.games[game_id] = {
                    "id": game_id,
                    "name": name,
                    "description": description,
                    "prompt_id": prompt_id
                }
                
                logger.info(f"Detected game: {game_id} - {name}")
    
    def get_prompt(self, prompt_id: str) -> str:
        """Get a prompt by ID"""
        return self.prompts.get(prompt_id, "")
    
    def get_game_prompt(self, game_id: str) -> str:
        """Get a game prompt by game ID"""
        if game_id in self.games:
            prompt_id = self.games[game_id]["prompt_id"]
            return self.prompts.get(prompt_id, "")
        return ""
    
    def get_all_games(self) -> Dict[str, Dict]:
        """Get metadata for all available games"""
        return self.games
    
    def replace_user_templates(self, text: str, user_data: Dict[str, Any]) -> str:
        """
        Replace user template variables (${user.field}) with actual values
        
        Args:
            text: The text containing templates
            user_data: Dictionary with user data
            
        Returns:
            Text with templates replaced by user values
        """
        if not text:
            return text
            
        # Define regex pattern for ${user.field} templates
        pattern = r'\${user\.([a-zA-Z]+)}'
        
        def replace_match(match):
            field = match.group(1)
            value = user_data.get(field)
            return str(value) if value is not None else f"[unknown {field}]"
        
        # Replace all matches
        return re.sub(pattern, replace_match, text)
    
    def track_vocabulary(self, user_id: str, word: str, translation: str, context: str = ""):
        """
        Track vocabulary word for a user
        
        Args:
            user_id: User ID
            word: Spanish vocabulary word
            translation: English translation
            context: Context in which the word was learned
            
        Returns:
            Success status
        """
        from app.firebase_service import add_user_to_firestore
        import time
        
        try:
            # Get existing vocabulary
            user_data = self.get_user_data(user_id)
            vocabulary = user_data.get("vocabulary", {})
            
            # Add new word
            vocabulary[word] = {
                "translation": translation,
                "context": context,
                "timestamp": time.time()
            }
            
            # Update user data
            success = add_user_to_firestore(
                user_id=user_id,
                vocabulary=vocabulary
            )
            
            return success
        except Exception as e:
            logger.error(f"Error tracking vocabulary: {e}")
            return False
    
    def get_user_data(self, user_id: str) -> Dict:
        """Get user data including vocabulary"""
        from app.firebase_service import get_user_from_firestore
        
        user_data = get_user_from_firestore(user_id) or {}
        return user_data