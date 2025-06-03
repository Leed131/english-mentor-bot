import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp
import tempfile
import requests
from pydub import AudioSegment

# Ключи
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# 🔍 Распознавание текста с изображения
async def recognize_text_from_image(url):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": "Please extract all readable text from this image and return it."}
            ]
        }],
        max_tokens=1000
    )
    return response.choices[0].message.content.strip()

# 🧠 Получение ответа от GPT
async def generate_response(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

# 🗣️ Генерация голосового ответа
async def generate_speech(text):
    speech_response = client.audio.speech.create(
        model="tts-1-hd",
        voice="alloy",  # реалистичный мужской британский голос
        input=text
    )
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    with open(temp_file.name, "wb") as f:
        f.write(speech_response.content)
    return temp_file.name

# 🎧 Распознавание аудио
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

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    SUPPORTED_AUDIO = (".mp3", ".wav", ".m4a", ".ogg")
    SUPPORTED_IMAGES = (".jpg", ".jpeg", ".png")

    for attachment in message.attachments:
        filename = attachment.filename.lower()

        # Обработка изображений
        if filename.endswith(SUPPORTED_IMAGES):
            await message.channel.send("🖼️ Processing image...")
            try:
                result = await recognize_text_from_image(attachment.url)
                await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
            except Exception as e:
                await message.channel.send(f"⚠️ Error reading image: {e}")

        # Обработка аудио
        elif filename.endswith(SUPPORTED_AUDIO):
            await message.channel.send("🎙️ Transcribing audio...")
            try:
                text = await transcribe_audio(attachment.url)
                await message.channel.send(f"📝 Transcription:\n{text}")

                reply = await generate_response(text)
                speech_path = await generate_speech(reply)

                await message.channel.send(f"💬 {reply}")
                await message.channel.send(file=discord.File(speech_path, filename="response.mp3"))
            except Exception as e:
                await message.channel.send(f"⚠️ Error processing audio: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
