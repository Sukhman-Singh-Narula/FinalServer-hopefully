Install ffmpeg on system
redis install using docker
npm i
python run.py
python start_workers.py


run 1. run.py
    2. start_workers.py
    3. monitor_worker.py

Step 1: ESP Device Connection & Authentication
When an ESP device connects:

The ESP device establishes a WebSocket connection to the FastAPI server
The connection includes a user ID parameter in the URL: /ws/{user_id}
The FastAPI server authenticates the user by:

Checking Redis for cached user data using the user ID
If not found in cache, querying Firebase for user profile
Storing user data in Redis cache for future quick access


The server creates a session and stores the WebSocket connection reference

Step 2: Audio Data Flow from ESP to Server
When the user speaks:

The ESP device captures audio and streams it in chunks via WebSocket
The FastAPI server receives these audio chunks in the WebSocket handler
The server does not process the audio directly in the WebSocket handler
Instead, the audio data is temporarily stored in Redis:
pythonaudio_key = f"audio:{session_id}:{uuid.uuid4()}"
await redis_client.set(audio_key, audio_data, ex=60)  # Expires after 60 seconds

The server then publishes a notification message to Redis PubSub:
pythonawait redis_client.publish(
    "audio:processing",  # Channel name
    json.dumps({
        "session_id": session_id,
        "audio_key": audio_key  # Reference to where audio is stored
    })
)


Step 3: Background Worker Processing
The background workers:

Are separate processes or tasks running alongside the main FastAPI server
Subscribe to Redis PubSub channels for work notifications
Obtain audio data from Redis using the key provided in the notification:
python# Worker code
async for message in pubsub.listen():
    if message["type"] == "message":
        data = json.loads(message["data"])
        audio_key = data.get("audio_key")
        
        # Get the actual audio bytes from Redis storage
        audio_data = await redis_client.get(audio_key)

Process the audio data to get transcription (using OpenAI API)
Run the workflow engine with the transcription
Generate text responses through the AI model
Convert text to speech (again using OpenAI or another TTS service)
Store the audio response in Redis:
pythonresponse_audio_key = f"response:{session_id}:{uuid.uuid4()}"
await redis_client.set(response_audio_key, audio_response, ex=60)

Publish a notification that a response is ready:
pythonawait redis_client.publish(
    f"responses:{session_id}",  # Channel specific to this session
    json.dumps({
        "type": "audio_response",
        "audio_key": response_audio_key  # Reference to audio data
    })
)


Step 4: Response Delivery to ESP Device
When a response is ready:

A dedicated response handler task (running in the FastAPI server) is already listening to the session's response channel
This handler receives the notification about the available response
It retrieves the audio data from Redis using the provided key:
python# Response handler code (running in server)
audio_key = data.get("audio_key")
audio_data = await redis_client.get(audio_key)

It sends the audio data back to the ESP device through the WebSocket:
pythonawait websocket.send_bytes(audio_data)

It cleans up by deleting the temporary audio data from Redis

How Redis PubSub, Background Workers, and Server Are Connected
The three components are connected in this way:

Server to Background Workers:

Server publishes messages to channels like audio:processing
Background workers subscribe to these channels to receive work
Messages contain references to data (keys) stored in Redis, not the data itself


Background Workers to Server:

Workers publish messages to session-specific channels like responses:{session_id}
Each active WebSocket connection has a dedicated response handler task
These response handlers subscribe to the session-specific channel
Again, messages contain references to data in Redis, not the actual data


Data Storage in Redis:

Audio data (both input and output) is stored temporarily in Redis
This avoids sending large binary data through PubSub channels
Both server and workers access the same Redis instance to store/retrieve data



Architectural View
ESP Device
   │
   │ WebSocket (audio data)
   ▼
FastAPI Server ◄───────────┐
   │                       │
   │ 1. Store audio in Redis
   │ 2. Publish notification
   │                       │
   │ Redis PubSub          │ Redis PubSub
   ▼                       │
Background Workers         │
   │                       │
   │ 1. Get audio from Redis
   │ 2. Process audio      │
   │ 3. Store response in Redis
   │ 4. Publish notification
   │                       │
   └───────────────────────┘
Benefits of This Flow
This architecture provides several advantages:

WebSocket handlers remain lightweight - They don't do heavy processing, just message passing
Background workers can scale independently - Add more workers for more processing power
Audio data doesn't clog PubSub channels - Only references are passed, not binary data
Fault tolerance - If a worker crashes, the data is still in Redis and can be processed by another worker
Session isolation - Each user session has its own response channel

This approach gives you a clean separation of concerns while maintaining the simplicity of Redis for both data storage and messaging.


