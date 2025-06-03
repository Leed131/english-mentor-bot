import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp
from gtts import gTTS

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

async def recognize_text_from_image(url):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": "Please extract all readable text from this image and return it."}
                ]
            }
        ],
        max_tokens=1000
    )
    return response.choices[0].message.content.strip()

async def transcribe_audio(file_path):
    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
    return transcript.text

def text_to_speech(text, filename):
    tts = gTTS(text)
    tts.save(filename)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Обработка изображений
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🔍 Scanning your image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                    text_to_speech(result, "response.mp3")
                    await message.channel.send(file=discord.File("response.mp3"))
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")
            elif attachment.filename.lower().endswith((".mp3", ".wav", ".m4a")):
                await message.channel.send("🎧 Transcribing audio...")
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            if resp.status == 200:
                                with open("temp_audio.mp3", "wb") as f:
                                    f.write(await resp.read())
                    transcript = await transcribe_audio("temp_audio.mp3")
                    await message.channel.send(f"📝 Transcription:\n{transcript}")
                    text_to_speech(transcript, "response.mp3")
                    await message.channel.send(file=discord.File("response.mp3"))
                except Exception as e:
                    await message.channel.send(f"⚠️ Error transcribing audio: {e}")

    # Ответ на текст
    if message.content:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": message.content}]
        )
        reply = response.choices[0].message.content.strip()
        await message.channel.send(reply)
        text_to_speech(reply, "response.mp3")
        await message.channel.send(file=discord.File("response.mp3"))

    await bot.process_commands(message)

bot.run(TOKEN)
