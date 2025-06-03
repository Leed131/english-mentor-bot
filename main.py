import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# 🖼️ Обработка изображения
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

# 🎧 Распознавание аудио (только mp3/wav)
async def transcribe_audio_from_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            audio_data = await resp.read()

    with open("temp_audio.mp3", "wb") as f:
        f.write(audio_data)

    with open("temp_audio.mp3", "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
    return transcript.text

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Обработка изображений
    if message.attachments:
        for attachment in message.attachments:
            filename = attachment.filename.lower()
            url = attachment.url

            # 📷 Обработка изображения
            if filename.endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🔍 Scanning your image...")
                try:
                    result = await recognize_text_from_image(url)
                    await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")

            # 🎧 Обработка аудио
            elif filename.endswith((".mp3", ".wav")):
                await message.channel.send("🎧 Transcribing audio...")
                try:
                    transcription = await transcribe_audio_from_url(url)
                    await message.channel.send(f"📝 Transcription:\n{transcription}")
                except Exception as e:
                    await message.channel.send(f"⚠️ Audio error: {e}")
            else:
                await message.channel.send("⚠️ Unsupported file format. Use .jpg, .png, .mp3 or .wav.")

    # Ответ на обычный текст
    if message.content:
        try:
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": message.content}
                ]
            )
            await message.channel.send(completion.choices[0].message.content.strip())
        except Exception as e:
            await message.channel.send(f"⚠️ Text error: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
