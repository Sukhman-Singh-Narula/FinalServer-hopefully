# run.py
import asyncio
import logging
import uvicorn
from app.main import app
from app.redis.redis_client import get_redis_client
# from app.syllabus_manager import SyllabusManager
from app.redis.workflow_engine import WorkflowEngine

async def setup():
    """Perform setup tasks before starting server"""
    # Initialize Redis connection
    redis = await get_redis_client()
    
    # Load syllabus into Redis
    # syllabus = SyllabusManager("./syllabus")
    # await syllabus.load_syllabus_to_redis()
    
    logging.info("Setup complete")

if __name__ == "__main__":
    # Run setup tasks
    asyncio.run(setup())
    
    # Start FastAPI server
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)