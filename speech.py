import tempfile
import requests
from openai import OpenAI
import os
from pydub import AudioSegment

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def transcribe_audio(url):
    response = requests.get(url)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio:
        temp_audio.write(response.content)
        temp_audio.flush()

        audio = AudioSegment.from_file(temp_audio.name)
        wav_path = temp_audio.name.replace(".mp3", ".wav")
        audio.export(wav_path, format="wav")

        with open(wav_path, "rb") as f:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
        return transcript.text

async def generate_speech(text):
    speech = client.audio.speech.create(
        model="tts-1-hd",
        voice="alloy",
        input=text
    )
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    with open(temp_file.name, "wb") as f:
        f.write(speech.content)
    return temp_file.name
