import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp
from gtts import gTTS
from discord import File
import tempfile

# Инициализация OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

# Настройка Discord-бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# Генерация голосового ответа
async def speak_and_send(text, message):
    tts = gTTS(text)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        tts.save(fp.name)
        await message.channel.send(file=File(fp.name, filename="response.mp3"))

# Распознавание текста с изображений
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

# Распознавание речи из аудио
async def transcribe_audio(file_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            audio_bytes = await resp.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
        temp_audio.write(audio_bytes)
        temp_audio_path = temp_audio.name

    with open(temp_audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
        return transcript.text

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.attachments:
        for attachment in message.attachments:
            filename = attachment.filename.lower()

            # Распознавание изображения
            if filename.endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🖼️ Scanning your image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                    await speak_and_send(result, message)
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")

            # Распознавание аудио
            elif filename.endswith(".mp3"):
                await message.channel.send("🗣️ Transcribing audio...")
                try:
                    text = await transcribe_audio(attachment.url)
                    await message.channel.send(f"📝 Transcription:\n{text}")
                    response_text = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": text}],
                        max_tokens=1000
                    ).choices[0].message.content.strip()

                    await message.channel.send(response_text)
                    await speak_and_send(response_text, message)

                except Exception as e:
                    await message.channel.send(f"⚠️ Audio error: {e}")

    # Ответ на текстовое сообщение
    elif message.content:
        response_text = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": message.content}],
            max_tokens=1000
        ).choices[0].message.content.strip()

        await message.channel.send(response_text)
        await speak_and_send(response_text, message)

    await bot.process_commands(message)

bot.run(TOKEN)
