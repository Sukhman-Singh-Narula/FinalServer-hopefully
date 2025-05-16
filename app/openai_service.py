# app/openai_service.py
import os
import logging
import time
import asyncio
import json
from typing import Dict, List, Optional, AsyncGenerator, Union
from openai import AsyncOpenAI, OpenAI
from app.config import OPENAI_API_KEY

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# OpenAI client instances
_sync_client = None
_async_client = None

def get_openai_client():
    """Get or create synchronized OpenAI client instance"""
    global _sync_client
    if _sync_client is None:
        _sync_client = OpenAI(api_key=OPENAI_API_KEY)
    return _sync_client

async def get_async_openai_client():
    """Get or create async OpenAI client instance"""
    global _async_client
    if _async_client is None:
        _async_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _async_client

async def transcribe_audio(audio_data: bytes, prompt: Optional[str] = None) -> str:
    """
    Transcribe audio data using OpenAI Whisper API
    
    Args:
        audio_data: WAV audio bytes
        prompt: Optional prompt to guide transcription
        
    Returns:
        Transcribed text
    """
    client = await get_async_openai_client()
    
    try:
        # Create a temporary file to store the audio
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as temp_file:
            temp_file.write(audio_data)
            temp_file.flush()
            
            # Open the file in read mode for the API
            with open(temp_file.name, "rb") as audio_file:
                # Call the OpenAI API
                response = await client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-1",
                    prompt=prompt
                )
                
                transcription = response.text
                logger.info(f"Transcription: {transcription[:50]}...")
                return transcription
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        return ""

async def generate_response(
    messages: List[Dict], 
    tools: Optional[List] = None, 
    model: str = "gpt-4o"
) -> Dict:
    """
    Generate a response using OpenAI API
    
    Args:
        messages: List of message objects (role, content)
        tools: Optional list of tools/functions
        model: Model to use
        
    Returns:
        Complete response object
    """
    client = await get_async_openai_client()
    
    params = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }
    
    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"
    
    try:
        response = await client.chat.completions.create(**params)
        return response.dict()
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return {"error": str(e)}

async def generate_streaming_response(
    messages: List[Dict], 
    tools: Optional[List] = None, 
    model: str = "gpt-4o"
) -> AsyncGenerator[str, None]:
    """
    Generate a streaming response using OpenAI API
    
    Args:
        messages: List of message objects (role, content)
        tools: Optional list of tools/functions
        model: Model to use
        
    Yields:
        Text chunks as they are generated
    """
    client = await get_async_openai_client()
    
    params = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "stream": True
    }
    
    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"
    
    try:
        stream = await client.chat.completions.create(**params)
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        logger.error(f"Error generating streaming response: {e}")
        yield f"I'm sorry, I encountered an error: {str(e)}"

async def generate_speech(
    text: str, 
    voice: str = "alloy", 
    model: str = "tts-1"
) -> bytes:
    """
    Generate speech from text using OpenAI API
    
    Args:
        text: Text to convert to speech
        voice: Voice to use
        model: Model to use
        
    Returns:
        MP3 audio bytes
    """
    client = await get_async_openai_client()
    
    try:
        response = await client.audio.speech.create(
            model=model,
            voice=voice,
            input=text
        )
        
        # Get the binary content
        audio_data = await response.read()
        return audio_data
    except Exception as e:
        logger.error(f"Error generating speech: {e}")
        return bytes()