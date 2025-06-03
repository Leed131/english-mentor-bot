import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp
import asyncio
from pydub import AudioSegment

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# Image-to-text
async def recognize_text_from_image(url):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": "Extract all readable English text from this image."}
            ]
        }],
        max_tokens=1000
    )
    return response.choices[0].message.content.strip()

# Audio-to-text (speech recognition)
async def transcribe_audio(file_path):
    with open(file_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
    return transcript.text

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Image handling
    if message.attachments:
        for attachment in message.attachments:
            filename = attachment.filename.lower()
            url = attachment.url

            if filename.endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🔍 Scanning image...")
                try:
                    result = await recognize_text_from_image(url)
                    await message.channel.send(f"📝 Text from image:\n```{result[:1900]}```")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")

            elif filename.endswith((".mp3", ".wav", ".m4a", ".ogg", ".webm")):
                await message.channel.send("🔊 Transcribing audio...")
                try:
                    # Download
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            audio_data = await resp.read()
                    with open("temp.webm", "wb") as f:
                        f.write(audio_data)

                    # Convert to mp3
                    sound = AudioSegment.from_file("temp.webm")
                    sound.export("temp.mp3", format="mp3")

                    text = await transcribe_audio("temp.mp3")
                    await message.channel.send(f"🎧 Transcription:\n```{text[:1900]}```")

                except Exception as e:
                    await message.channel.send(f"⚠️ Error with audio: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
