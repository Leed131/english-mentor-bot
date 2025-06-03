import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp
import asyncio
import tempfile
import requests

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# Распознавание текста с изображений
async def recognize_text_from_image(url):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": "Please extract all readable text from this image."}
                ]
            }
        ],
        max_tokens=1000
    )
    return response.choices[0].message.content.strip()

# Распознавание речи из аудио
async def transcribe_audio_from_url(url):
    response = requests.get(url)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name
    with open(tmp_path, "rb") as f:
        transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
        return transcript.text

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Обработка изображений
    if message.attachments:
        for attachment in message.attachments:
            fname = attachment.filename.lower()
            if fname.endswith((".jpg", ".jpeg", ".png")):
                await message.channel.send("🖼 Scanning image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📄 Extracted text:\n{result[:1900]}")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")
            elif fname.endswith((".mp3", ".wav", ".ogg")):
                await message.channel.send("🎙 Transcribing audio...")
                try:
                    transcript = await transcribe_audio_from_url(attachment.url)
                    await message.channel.send(f"📝 Transcription:\n`{transcript}`")

                    # Ответ на распознанный текст
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": transcript}]
                    )
                    await message.channel.send(f"💬 {response.choices[0].message.content}")
                except Exception as e:
                    await message.channel.send(f"⚠️ Audio error: {e}")

    # Обработка текстовых сообщений
    elif message.content:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": message.content}]
        )
        await message.channel.send(response.choices[0].message.content)

    await bot.process_commands(message)

bot.run(TOKEN)
