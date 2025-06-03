import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp
import tempfile
from pydub import AudioSegment

# Ключи
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

# Настройка бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# 🖼️ Распознавание текста с изображения
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

# 🎧 Распознавание речи
async def transcribe_audio(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(await resp.read())
                mp3_path = f.name

    audio = AudioSegment.from_file(mp3_path)
    wav_path = mp3_path.replace(".mp3", ".wav")
    audio.export(wav_path, format="wav")

    with open(wav_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
    return transcript.text

# 🔊 Генерация речи
def generate_speech(text):
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text
    )
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        response.stream_to_file(f.name)
        return f.name

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Обработка вложений
    if message.attachments:
        for attachment in message.attachments:
            filename = attachment.filename.lower()

            # 🖼️ Картинка
            if filename.endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🖼️ Scanning image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📖 I found:\n```{result[:1900]}```")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")

            # 🎧 Аудио
            elif filename.endswith(".mp3"):
                await message.channel.send("🎧 Transcribing audio...")
                try:
                    text = await transcribe_audio(attachment.url)
                    await message.channel.send(f"📝 You said: `{text}`")

                    # Получаем голосовой ответ
                    completion = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role": "user", "content": text}]
                    )
                    reply = completion.choices[0].message.content
                    tts_path = generate_speech(reply)
                    await message.channel.send("🔊", file=discord.File(tts_path))
                except Exception as e:
                    await message.channel.send(f"⚠️ Error transcribing audio: {e}")

    # 💬 Текстовое сообщение
    elif message.content:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": message.content}]
        )
        reply = completion.choices[0].message.content
        await message.channel.send(reply)

    await bot.process_commands(message)

bot.run(TOKEN)
