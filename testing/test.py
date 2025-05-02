import asyncio
import websockets
import os
import random
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Server configuration
SERVER_HOST = os.getenv("SERVER_HOST", "localhost")
SERVER_PORT = int(os.getenv("SERVER_PORT", 8000))

# Test data configuration
CHUNK_SIZE = 1024  # Size of each audio chunk in bytes
TOTAL_CHUNKS = 20  # Number of chunks to send
DELAY_BETWEEN_CHUNKS = 0.1  # Delay in seconds

async def send_test_audio():
    # Generate a test device ID
    device_id = f"TEST_DEVICE_{random.randint(1000, 9999)}"
    
    # Connect to WebSocket server
    uri = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws/{device_id}"
    print(f"Connecting to {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            # Wait for welcome message
            response = await websocket.recv()
            print(f"Server response: {response}")
            
            # Send audio chunks
            print(f"Sending {TOTAL_CHUNKS} audio chunks of {CHUNK_SIZE} bytes each...")
            
            for i in range(TOTAL_CHUNKS):
                # Generate random audio data
                audio_data = os.urandom(CHUNK_SIZE)
                
                # Send the audio chunk
                await websocket.send(audio_data)
                print(f"Sent chunk {i+1}/{TOTAL_CHUNKS}: {len(audio_data)} bytes")
                
                # Small delay to simulate real-time audio
                await asyncio.sleep(DELAY_BETWEEN_CHUNKS)
            
            # Send end stream command
            end_command = json.dumps({"type": "end_stream"})
            await websocket.send(end_command)
            print("Sent end_stream command")
            
            # Wait for confirmation
            response = await websocket.recv()
            print(f"Server response: {response}")
            
            print("Test completed successfully!")
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(send_test_audio())