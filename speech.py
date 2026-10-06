import asyncio
import os
import tempfile
import wave
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


async def generate_speech(
    text: str,
    *,
    voice: str = "alloy",
    instructions: str | None = None,
    response_format: str = "mp3",
) -> str:
    request = {
        "model": "gpt-4o-mini-tts",
        "voice": voice,
        "input": text,
        "response_format": response_format,
    }
    if instructions:
        request["instructions"] = instructions

    speech_response = await _get_client().audio.speech.create(**request)

    suffix = "." + response_format.lower().lstrip(".")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = temp_file.name

    # This small local write cannot outlive the SDK response object.
    with open(temp_path, "wb") as output_file:  # noqa: ASYNC230
        output_file.write(speech_response.content)

    return temp_path


def _merge_wav_files(paths: list[str], pause_ms: int = 250) -> str:
    if not paths:
        raise ValueError("No audio files to merge")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as output:
        output_path = output.name

    reference = None
    with wave.open(output_path, "wb") as writer:
        for index, path in enumerate(paths):
            with wave.open(path, "rb") as reader:
                params = (
                    reader.getnchannels(),
                    reader.getsampwidth(),
                    reader.getframerate(),
                    reader.getcomptype(),
                )
                if reference is None:
                    reference = params
                    writer.setnchannels(params[0])
                    writer.setsampwidth(params[1])
                    writer.setframerate(params[2])
                    writer.setcomptype(params[3], reader.getcompname())
                elif params != reference:
                    raise RuntimeError("Dialogue TTS returned incompatible WAV formats")

                writer.writeframes(reader.readframes(reader.getnframes()))

                if index < len(paths) - 1 and pause_ms > 0:
                    frame_count = round(params[2] * pause_ms / 1000)
                    silence = b"\x00" * frame_count * params[0] * params[1]
                    writer.writeframes(silence)

    return output_path


async def generate_dialogue_speech(
    turns: list[tuple[int, str]],
    *,
    voices: tuple[str, str] = ("marin", "cedar"),
) -> str:
    """Generate a two-speaker learner-friendly Danish dialogue as one WAV file."""
    if not turns:
        raise ValueError("Dialogue has no turns")

    instruction = (
        "Speak only the supplied Danish text. Use clear, natural Danish pronunciation "
        "at a calm learner-friendly pace. Do not translate, explain, add speaker names, "
        "or add any words."
    )
    tasks = [
        generate_speech(
            text,
            voice=voices[speaker_index % len(voices)],
            instructions=instruction,
            response_format="wav",
        )
        for speaker_index, text in turns
    ]
    paths = await asyncio.gather(*tasks)

    try:
        return _merge_wav_files(paths)
    finally:
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
