import os
import discord
from discord.ext import commands
import aiohttp
from openai import OpenAI
import edge_tts
from pydub import AudioSegment
import asyncio
import tempfile

# OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

# Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")

# Image-to-text via GPT-4o
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

# Voice transcription (whisper)
async def transcribe_audio(file_path):
    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
        return transcript.text

# Text-to-speech (edge-tts)
async def generate_tts(text, output_path):
    communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
    await communicate.save(output_path)

# Respond to messages
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Handle image attachments
    if message.attachments:
        for attachment in message.attachments:
            filename = attachment.filename.lower()

            # 📷 Image recognition
            if filename.endswith((".jpg", ".jpeg", ".png")):
                await message.channel.send("🖼 Scanning image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                except Exception as e:
                    await message.channel.send(f"⚠️ Image error: {e}")

            # 🎙 Audio recognition
            elif filename.endswith((".mp3", ".wav", ".m4a")):
                await message.channel.send("🎧 Transcribing audio...")
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                                temp_audio.write(await resp.read())
                                temp_audio_path = temp_audio.name

                    transcription = await transcribe_audio(temp_audio_path)
                    await message.channel.send(f"📝 Transcription:\n```{transcription}```")

                    # Get response from GPT
                    reply = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "You're an English mentor."},
                            {"role": "user", "content": transcription}
                        ]
                    ).choices[0].message.content

                    await message.channel.send(f"💬 {reply}")

                    # Text-to-speech
                    tts_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
                    await generate_tts(reply, tts_path)
                    await message.channel.send(file=discord.File(tts_path, filename="response.mp3"))

                except Exception as e:
                    await message.channel.send(f"⚠️ Audio error: {e}")

    # Handle text messages
    elif message.content:
        reply = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You're an English mentor."},
                {"role": "user", "content": message.content}
            ]
        ).choices[0].message.content

        await message.channel.send(f"💬 {reply}")

        # Text-to-speech
        tts_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        await generate_tts(reply, tts_path)
        await message.channel.send(file=discord.File(tts_path, filename="response.mp3"))

    await bot.process_commands(message)

bot.run(TOKEN)
