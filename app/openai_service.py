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