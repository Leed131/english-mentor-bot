import asyncio
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None
SUPPORTED_AUDIO_SUFFIXES = {
    ".flac",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".ogg",
    ".wav",
    ".webm",
}


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


def _audio_suffix_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in SUPPORTED_AUDIO_SUFFIXES:
        return suffix
    return ".mp3"


async def transcribe_audio_file(path: str, language: str | None = None) -> str:
    # The SDK needs an open file object for the duration of the awaited upload.
    with open(path, "rb") as audio_file:  # noqa: ASYNC230
        request = {
            "model": "whisper-1",
            "file": audio_file,
        }
        if language:
            request["language"] = language

        transcript = await _get_client().audio.transcriptions.create(**request)

    text = transcript.text.strip()
    if not text:
        raise RuntimeError("OpenAI returned an empty transcription")
    return text


async def transcribe_audio(url: str, language: str | None = None) -> str:
    response = await asyncio.to_thread(requests.get, url, timeout=30)
    response.raise_for_status()

    suffix = _audio_suffix_from_url(url)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_audio:
            temp_audio.write(response.content)
            temp_path = temp_audio.name

        return await transcribe_audio_file(temp_path, language=language)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


async def generate_speech(text: str) -> str:
    speech_response = await _get_client().audio.speech.create(
        model="tts-1-hd",
        voice="alloy",
        input=text,
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
        temp_path = temp_file.name

    # This small local write cannot outlive the SDK response object.
    with open(temp_path, "wb") as output_file:  # noqa: ASYNC230
        output_file.write(speech_response.content)

    return temp_path
