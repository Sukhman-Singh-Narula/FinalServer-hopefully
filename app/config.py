# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# Firebase configuration
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Audio settings
SAMPLE_RATE = 24000
AUDIO_CHANNELS = 1