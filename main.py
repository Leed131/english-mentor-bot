import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp
import asyncio
from pydub import AudioSegment
import uuid

# Инициализация OpenAI и Discord токенов
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

# Настройки Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# 🎨 Распознавание текста с изображений
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

# 🎧 Распознавание речи из .ogg файла
async def transcribe_audio_from_ogg(url):
    ogg_path = f"{uuid.uuid4()}.ogg"
    mp3_path = ogg_path.replace(".ogg", ".mp3")

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            with open(ogg_path, "wb") as f:
                f.write(await resp.read())

    # Конвертация .ogg → .mp3
    AudioSegment.from_ogg(ogg_path).export(mp3_path, format="mp3")

    # Отправка в OpenAI для транскрипции
    with open(mp3_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
    
    os.remove(ogg_path)
    os.remove(mp3_path)
    return transcript.text

# 📥 Обработка всех типов сообщений
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.attachments:
        for attachment in message.attachments:
            filename = attachment.filename.lower()

            # 🖼️ Картинка
            if filename.endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🔍 Scanning your image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")

            # 🎧 Голосовое сообщение
            elif filename.endswith(".ogg"):
                await message.channel.send("🎙️ Transcribing audio...")
                try:
                    transcript = await transcribe_audio_from_ogg(attachment.url)
await message.channel.send(f"📝 Transcription:\n{transcript}")

# Ответ на аудиосообщение GPT-4o
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": transcript}
    ]
)
await message.channel.send(f"💬 {response.choices[0].message.content}")

                    # Ответ на содержание аудио
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": transcript}]
                    )
                    await message.channel.send(f"💬 {response.choices[0].message.content}")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error transcribing audio: {e}")

            else:
                await message.channel.send("⚠️ Unsupported file format. Use .jpg, .png, or .ogg")

    await bot.process_commands(message)

bot.run(TOKEN)
