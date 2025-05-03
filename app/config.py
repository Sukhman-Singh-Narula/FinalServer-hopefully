# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
SAMPLE_RATE = 8000
CHANNELS = 1
SAMPLE_WIDTH = 2
# Firebase configuration
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")