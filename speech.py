import asyncio
import os
import tempfile

import requests
from openai import AsyncOpenAI
from pydub import AudioSegment


client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _convert_to_wav(source_path, wav_path):
    audio = AudioSegment.from_file(source_path)
    audio.export(wav_path, format="wav")


async def transcribe_audio(url):
    response = await asyncio.to_thread(requests.get, url, timeout=30)
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_audio:
        temp_audio.write(response.content)
        temp_audio.flush()

        wav_path = temp_audio.name.replace(".mp3", ".wav")
        await asyncio.to_thread(_convert_to_wav, temp_audio.name, wav_path)

        with open(wav_path, "rb") as f:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
            )
        return transcript.text


async def generate_speech(text):
    speech_response = await client.audio.speech.create(
        model="tts-1-hd",
        voice="alloy",
        input=text
    )
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    with open(temp_file.name, "wb") as f:
        f.write(speech_response.content)
    return temp_file.name
