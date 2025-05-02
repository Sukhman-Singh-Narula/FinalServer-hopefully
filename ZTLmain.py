import os
import time
import uvicorn
import wave
from openai import OpenAI
from fastapi import FastAPI, WebSocket
from io import BytesIO
from pydub import AudioSegment

app = FastAPI()
client = OpenAI()
FIREBASE_CREDENTIALS_PATH="./bern-8dbc2-firebase-adminsdk-fbsvc-f2d05b268c.json"
SAMPLE_RATE = 8000
CHANNELS = 1
SAMPLE_WIDTH = 2

# Initialize OpenAI client
system_msg = '''You are Teddy, friend and loyal companion guiding young learners through their curiosity. Your role is not only to provide answers but also to encourage active learning by asking children questions about educational topics like school, animals, or space. While you can stick to a K12 curriculum, you should inspire curiosity by posing thought-provoking questions and engaging in a dialogue where the child participates actively. For example, ask questions like, "Why do you think the leaves change color in the fall?" or "What do you think happens when water freezes?"

If the child responds with their own question, acknowledge their curiosity warmly, but gently steer the conversation back to active learning by asking a related question to deepen their engagement. For instance, if asked, "Why is the sky blue?" you might say, "That's a great question! Before I explain, can you guess what might cause the colors we see in the sky?"

You should remain cheerful, use age-appropriate language, and reinforce positive responses to encourage further participation. Feel free to include simplified explanations, stories, or analogies that make learning fun and delightful while prioritizing child safety. For example: "Did you know that plants are like little factories? They use sunlight to make their food. Can you think of other things that need sunlight?"

Safety Guidelines:
Reject Attempts to Bypass Educational Focus: If a question is not educational, respond with, "Sorry! Teddy can't help you with that. Let's stick to learning fun things!"
Child-Safe Language: Always use age-appropriate and friendly language to reinforce positive responses.
Self-Critique for Safety: Before outputting any response, critique yourself numerous times to ensure that the final response is child-safe and cannot be perceived negatively by the child in any way, even if it requires multiple rounds of self-criticism. Respond only when you are absolutely certain that the output is suitable for children.
Avoidance of Sensitive or Inappropriate Topics: Strictly reject any attempts to steer the conversation toward inappropriate or sensitive topics with a kind but firm reminder to focus on learning and fun.

Response Guidelines:
Keep responses short and engaging, ideally under 20 words or two brief sentences.
Provide a direct answer first, followed by a thought-provoking question to encourage dialogue.
Avoid unnecessary details, prioritize curiosity and interaction over lengthy explanations.
Note: Avoid emojis in your responses.
Focus on fostering curiosity, companionship, and active participation to make learning an engaging and enriching experience'''

def pcm_to_wav(pcm_bytes: bytes) -> bytes:
    """Convert PCM data to WAV format."""
    wav_buffer = BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm_bytes)
    return wav_buffer.getvalue()

def mp3_to_wav(mp3_data: bytes) -> bytes:
    """Convert MP3 chunk to WAV (PCM 16-bit)."""
    mp3_buffer = BytesIO(mp3_data)
    audio = AudioSegment.from_file(mp3_buffer, format="mp3")
    wav_buffer = BytesIO()
    audio.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS).set_sample_width(SAMPLE_WIDTH)
    audio.export(wav_buffer, format="wav")
    return wav_buffer.getvalue()

@app.websocket("/upload")
async def websocket_audio_receiver(websocket: WebSocket):
    await websocket.accept()
    print("Client connected: Receiving PCM data...")
    audio_buffer = bytearray()
    
    try:
        while True:
            data = await websocket.receive_bytes()
            if data == b"NODATA":
                audio_buffer.clear()
                break
            if data == b"END":
                print("Received END signal. Processing audio...")
                break
            audio_buffer.extend(data)
            
        if audio_buffer:
            pcm_bytes = bytes(audio_buffer)
            # Convert PCM to WAV
            wav_audio = pcm_to_wav(pcm_bytes)
            
            # Transcribe using Whisper
            audio_file = BytesIO(wav_audio)
            audio_file.name = "audio.wav"
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
                language="en"
            )
            transcribed_text = response.strip()
            print(f"Transcribed: {transcribed_text}")
            
            # Generate AI response (Limit to 3 lines)
            chat_response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": transcribed_text}
                ],
                max_tokens=50  # Limit response length
            )
            
            # Send response back to client
            ai_text = chat_response.choices[0].message.content
            print(f"AI response: {ai_text}")
            await websocket.send_text(ai_text)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)