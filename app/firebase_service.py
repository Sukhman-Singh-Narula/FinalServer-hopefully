# app/firebase_service.py
import os
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from typing import Dict, Any, Optional, List
from app.config import FIREBASE_CREDENTIALS_PATH

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Firebase client instance
_firebase_app = None
_firestore_client = None

def initialize_firebase():
    """Initialize Firebase Admin SDK if not already initialized"""
    global _firebase_app, _firestore_client
    
    if _firebase_app is not None:
        return _firestore_client
    
    try:
        # Try to get the app if it's already initialized
        _firebase_app = firebase_admin.get_app()
    except ValueError:
        # Initialize it if not already done
        try:
            if not os.path.exists(FIREBASE_CREDENTIALS_PATH):
                logger.error(f"Firebase credentials file not found at {FIREBASE_CREDENTIALS_PATH}")
                return None
                
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Firebase initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Firebase: {e}")
            return None
    
    try:
        _firestore_client = firestore.client()
        return _firestore_client
    except Exception as e:
        logger.error(f"Error getting Firestore client: {e}")
        return None

def get_user_from_firestore(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve user information from Firestore
    
    Args:
        user_id: The ID of the user to retrieve
        
    Returns:
        Dictionary containing user data or None if not found
    """
    db = initialize_firebase()
    if not db:
        logger.error("Firebase not initialized. Cannot get user data.")
        return None
    
    try:
        user_doc = db.collection('Users').document(user_id).get()
        if user_doc.exists:
            return user_doc.to_dict()
        else:
            logger.info(f"User {user_id} not found in Firestore")
            # Return default empty user structure
            return {
                'name': None,
                'age': None,
                'language': 'Spanish',
                'proficiency': 'Beginner',
                'vocabulary': {}
            }
    except Exception as e:
        logger.error(f"Error retrieving user from Firestore: {e}")
        return None

def add_user_to_firestore(user_id: str, **user_data) -> bool:
    """Add or update user information in Firestore
    
    Args:
        user_id: The ID of the user to add/update
        **user_data: User information fields
        
    Returns:
        Boolean indicating success
    """
    db = initialize_firebase()
    if not db:
        logger.error("Firebase not initialized. Cannot save user data.")
        return False
    
    try:
        db.collection('Users').document(user_id).set(user_data, merge=True)
        logger.info(f"User {user_id} updated in Firestore")
        return True
    except Exception as e:
        logger.error(f"Error saving user to Firestore: {e}")
        return False

def get_all_prompts() -> Dict[str, str]:
    """Retrieve all prompts from Firestore
    
    Returns:
        Dictionary with prompt IDs as keys and content as values
    """
    db = initialize_firebase()
    if not db:
        logger.error("Firebase not initialized. Cannot get prompts.")
        return {}
    
    prompts = {}
    try:
        prompt_docs = db.collection("Prompts").stream()
        
        for doc in prompt_docs:
            prompt_id = doc.id
            prompt_content = doc.to_dict().get("content", "")
            prompts[prompt_id] = prompt_content
            logger.debug(f"Retrieved prompt: {prompt_id} ({len(prompt_content)} chars)")
        
        if not prompts:
            logger.warning("No prompts found in Firestore")
            
        return prompts
    except Exception as e:
        logger.error(f"Error retrieving prompts from Firestore: {e}")
        return {}

def save_vocabulary_word(user_id: str, word: str, translation: str, context: str = "") -> bool:
    """Save a vocabulary word for a user
    
    Args:
        user_id: The ID of the user
        word: Spanish vocabulary word
        translation: English translation
        context: Optional context about how the word was learned
        
    Returns:
        Boolean indicating success
    """
    db = initialize_firebase()
    if not db:
        logger.error("Firebase not initialized. Cannot save vocabulary.")
        return False
    
    try:
        # Get current vocabulary
        user_ref = db.collection('Users').document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            user_data = user_doc.to_dict()
            vocabulary = user_data.get('vocabulary', {})
        else:
            vocabulary = {}
        
        # Add new word
        vocabulary[word] = {
            "translation": translation,
            "context": context,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        
        # Update vocabulary
        user_ref.set({"vocabulary": vocabulary}, merge=True)
        
        logger.info(f"Vocabulary word '{word}' saved for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving vocabulary word: {e}")
        return False