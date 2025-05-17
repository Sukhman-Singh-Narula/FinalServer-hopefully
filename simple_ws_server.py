# simple_ws_server.py
import os
import asyncio
import uvicorn
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Simple WebSocket Test Server")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections = {}

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "ok"}

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await websocket.accept()
    
    logger.info(f"New WebSocket connection: device_id={device_id}")
    
    # Track this connection
    active_connections[device_id] = websocket
    
    # Send welcome message
    await websocket.send_text(json.dumps({
        "type": "info", 
        "message": f"Connected as device {device_id}"
    }))
    
    # Audio data buffer
    audio_buffer = bytearray()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive()
            
            if "bytes" in data:
                # Handle binary audio data
                audio_bytes = data["bytes"]
                
                # Append to buffer
                audio_buffer.extend(audio_bytes)
                logger.info(f"Received audio chunk: {len(audio_bytes)} bytes, total buffer: {len(audio_buffer)} bytes")
                
                # Send acknowledgment
                await websocket.send_text(json.dumps({
                    "type": "ack", 
                    "message": f"Received {len(audio_bytes)} bytes"
                }))
                
                # If buffer gets large enough, "process" it
                if len(audio_buffer) > 10000:
                    logger.info("Processing audio buffer...")
                    
                    # Simulate processing delay
                    await asyncio.sleep(1)
                    
                    # Send a text response (this simulates the AI response)
                    response_text = "I heard you speaking. This is a test response from the server."
                    await websocket.send_text(response_text)
                    
                    # Clear buffer
                    audio_buffer = bytearray()
                    
                    logger.info("Sent response to client")
                
            elif "text" in data:
                # Handle text commands
                try:
                    message = json.loads(data["text"])
                    logger.info(f"Received command: {message}")
                    
                    command_type = message.get("type")
                    
                    if command_type == "end_stream":
                        # Process any remaining audio
                        if len(audio_buffer) > 0:
                            logger.info(f"Processing final buffer of {len(audio_buffer)} bytes")
                            
                            # Simulate processing delay
                            await asyncio.sleep(1)
                            
                            # Send a text response
                            response_text = "This is the final response for your conversation."
                            await websocket.send_text(response_text)
                            
                            # Clear buffer
                            audio_buffer = bytearray()
                        
                        # Send acknowledgment
                        await websocket.send_text(json.dumps({
                            "type": "info",
                            "message": "Stream end acknowledged"
                        }))
                
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON"
                    }))
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {device_id}")
        # Clean up
        if device_id in active_connections:
            del active_connections[device_id]
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        # Clean up
        if device_id in active_connections:
            del active_connections[device_id]
            
    logger.info(f"WebSocket connection closed: {device_id}")

if __name__ == "__main__":
    logger.info("Starting WebSocket test server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)