#!/usr/bin/env python3

"""
Spanish Language Tutor System Test Client

This script:
1. Records audio from the microphone in real time
2. Sends it to the WebSocket server
3. Receives and plays back responses
4. Handles the conversation flow with the Spanish tutor

Usage:
  Simply run: python test_spanish.py
"""

import asyncio
import json
import numpy as np
import sounddevice as sd
import time
import websockets
from pydub import AudioSegment
from pydub.playback import play
from io import BytesIO
import os
import sys

# Audio settings (matching server configuration)
SAMPLE_RATE = 8000  # Sample rate in Hz
CHANNELS = 1        # Mono audio
CHUNK_SIZE = 1024   # Bytes per chunk
SAMPLE_WIDTH = 2    # 16-bit audio (2 bytes)
FORMAT = np.int16   # NumPy format for 16-bit audio

# Server settings
SERVER_URL = "ws://localhost:8000/ws"
DEVICE_ID = f"test_device_{int(time.time())}"  # Unique device ID based on timestamp

# Complete websocket URL
WEBSOCKET_URL = f"{SERVER_URL}/{DEVICE_ID}"

# Global variables for audio processing
audio_buffer = bytearray()
recording = False
should_exit = False

async def record_and_send_audio(websocket):
    """Record audio from microphone and send it to the WebSocket server"""
    global recording, audio_buffer, should_exit

    print(f"🎤 Press SPACE to start/stop recording, Q to quit")
    print(f"🔄 Connected to server as device_id: {DEVICE_ID}")

    # Setup audio stream
    stream = sd.InputStream(
        channels=CHANNELS,
        samplerate=SAMPLE_RATE,
        dtype=FORMAT,
        blocksize=CHUNK_SIZE // SAMPLE_WIDTH,
        callback=audio_callback
    )

    # Start the stream
    with stream:
        # Loop until user quits
        while not should_exit:
            # When recording is active, send audio data
            if recording and len(audio_buffer) >= CHUNK_SIZE:
                # Get chunk from buffer
                chunk = bytes(audio_buffer[:CHUNK_SIZE])
                audio_buffer = audio_buffer[CHUNK_SIZE:]

                # Send the chunk to WebSocket server
                await websocket.send(chunk)

                # Throttle slightly to avoid overwhelming the connection
                await asyncio.sleep(0.01)
            else:
                # If not recording or buffer too small, sleep briefly
                await asyncio.sleep(0.1)

        # End the session properly
        try:
            await websocket.send(json.dumps({
                "type": "end_stream",
                "message": "User ended session"
            }))
            print("Session ended gracefully")
        except:
            print("Could not send end_stream message, connection might be closed")

def audio_callback(indata, frames, time_info, status):
    """Callback function for audio stream"""
    global recording, audio_buffer
    
    if recording:
        # Convert float32 data to int16 PCM
        audio_data = indata.copy().astype(np.int16).tobytes()
        audio_buffer.extend(audio_data)

async def receive_messages(websocket):
    """Receive and process messages from the WebSocket server"""
    global recording, should_exit
    
    try:
        async for message in websocket:
            # Check if message is binary or text
            if isinstance(message, bytes):
                print(f"Received binary data: {len(message)} bytes")
                # This would be audio response from server if implemented
                play_audio(message)
            else:
                # Parse JSON message
                try:
                    data = json.loads(message)
                    message_type = data.get("type", "unknown")
                    
                    if message_type == "ack":
                        print(f"🟢 Server acknowledged: {data.get('message', '')}")
                    elif message_type == "agent_response":
                        # Spanish tutor text response
                        response = data.get("message", "")
                        print(f"\n🤖 Spanish Tutor: {response}\n")
                        # Convert response to speech and play (text-to-speech)
                        await text_to_speech_and_play(response)
                    elif message_type == "error":
                        print(f"❌ Error: {data.get('message', '')}")
                    elif message_type == "info":
                        print(f"ℹ️ Info: {data.get('message', '')}")
                    elif message_type == "session_ended":
                        print(f"🛑 Session ended: {data.get('message', '')}")
                    else:
                        print(f"📬 Received message: {message}")
                except json.JSONDecodeError:
                    print(f"Received non-JSON message: {message}")
    except websockets.exceptions.ConnectionClosedError:
        print("Connection to server closed")
        should_exit = True
    except Exception as e:
        print(f"Error in receive_messages: {e}")
        should_exit = True

async def text_to_speech_and_play(text):
    """Convert text to speech and play it"""
    try:
        # Using gTTS for text-to-speech (requires internet)
        from gtts import gTTS
        
        print("Converting tutor response to speech...")
        tts = gTTS(text=text, lang='en', slow=False)
        
        # Save to in-memory file
        fp = BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        
        # Convert to audio segment
        audio = AudioSegment.from_file(fp, format="mp3")
        
        # Play the audio
        play(audio)
        
    except ImportError:
        print("TTS not available. Install gTTS: pip install gtts")
    except Exception as e:
        print(f"Error in text_to_speech: {e}")

def play_audio(audio_data):
    """Play audio data received from server"""
    try:
        # Convert to WAV format using BytesIO
        wav_io = BytesIO()
        
        # Create WAV file in memory
        import wave
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio_data)
        
        # Reset position to start of buffer
        wav_io.seek(0)
        
        # Load with pydub and play
        audio = AudioSegment.from_wav(wav_io)
        play(audio)
    except Exception as e:
        print(f"Error playing audio: {e}")

async def handle_keyboard_input():
    """Handle keyboard input for controlling recording"""
    global recording, should_exit
    
    print("⌨️  Press Enter to start/stop recording, type 'q' to quit")
    
    while not should_exit:
        # Use asyncio.create_task for keyboard input to avoid blocking
        if sys.platform == 'win32':
            # Windows implementation
            import msvcrt
            await asyncio.sleep(0.1)  # Small sleep to prevent CPU spinning
            
            if msvcrt.kbhit():
                key = msvcrt.getch().decode('utf-8', errors='ignore')
                
                # Space toggles recording
                if key == ' ':
                    recording = not recording
                    print(f"🎤 Recording: {'ON' if recording else 'OFF'}")
                    
                    # Clear buffer when starting new recording
                    if recording:
                        audio_buffer.clear()
                        
                # Q quits the program
                elif key.lower() == 'q':
                    print("Exiting...")
                    should_exit = True
        else:
            # Unix implementation
            import aioconsole
            cmd = await aioconsole.ainput('> ')
            
            if cmd == '':  # Enter key
                recording = not recording
                print(f"🎤 Recording: {'ON' if recording else 'OFF'}")
                
                # Clear buffer when starting new recording
                if recording:
                    audio_buffer.clear()
            
            elif cmd.lower() == 'q':
                print("Exiting...")
                should_exit = True
            
            # Handle specific text commands for testing
            elif cmd.startswith('/'):
                # Send text input instead of audio
                text_input = cmd[1:]  # Remove the /
                await send_text_input(text_input)

async def send_text_input(text):
    """Send text input directly to the server (for testing without audio)"""
    try:
        async with websockets.connect(WEBSOCKET_URL) as ws:
            # Send the text command
            await ws.send(json.dumps({
                "type": "text_input",
                "content": text
            }))
            print(f"📤 Sent text input: {text}")
            
            # Wait for response
            response = await ws.recv()
            print(f"📥 Received response: {response}")
    except Exception as e:
        print(f"Error sending text input: {e}")

async def main():
    global should_exit
    
    print(f"Connecting to {WEBSOCKET_URL}")
    print("Spanish Language Tutor - Test Client")
    print("===================================")
    print("This client will record audio from your microphone and send it to the server.")
    print("The server will transcribe the audio, process it through the Spanish tutor,")
    print("and send back responses which will be played back to you.")
    print()
    print("Instructions:")
    print("- Press SPACE to start/stop recording")
    print("- Type 'q' and press Enter to quit")
    print()
    
    try:
        # Connect to WebSocket server
        async with websockets.connect(WEBSOCKET_URL) as websocket:
            # Start tasks for recording, receiving messages, and keyboard input
            record_task = asyncio.create_task(record_and_send_audio(websocket))
            receive_task = asyncio.create_task(receive_messages(websocket))
            keyboard_task = asyncio.create_task(handle_keyboard_input())
            
            # Wait for any task to complete
            try:
                done, pending = await asyncio.wait(
                    [record_task, receive_task, keyboard_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
            except Exception as e:
                print(f"Task error: {e}")
                should_exit = True
                
    except websockets.exceptions.ConnectionRefusedError:
        print(f"❌ Could not connect to the server at {WEBSOCKET_URL}")
        print("Make sure your server is running and the URL is correct")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Update exit flag
        should_exit = True

if __name__ == "__main__":
    # Run the main async function
    if sys.platform != 'win32':
        try:
            import aioconsole
        except ImportError:
            print("Please install aioconsole: pip install aioconsole")
            sys.exit(1)
            
    try:
        import gtts
    except ImportError:
        print("Warning: gTTS not installed. TTS will not work.")
        print("Install with: pip install gtts")
    
    asyncio.run(main())