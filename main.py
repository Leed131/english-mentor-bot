import os
import discord
import aiohttp
from discord.ext import commands
from openai import OpenAI

# Настройка OpenAI и Discord
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
        model="gpt-4-vision-preview",  # если выдаёт ошибку, замените на gpt-4o
        messages=[
            {
                "role": "user",
                "content": [
                    { "type": "image_url", "image_url": { "url": url } },
                    { "type": "text", "text": "Please extract all readable text from this image." }
                ]
            }
        ],
        max_tokens=1000
    )
    return response.choices[0].message.content.strip()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Ответ на обычный текст
    if message.content.startswith("!hello"):
        await message.channel.send("👋 Hello! Send me an image or message!")

    # Обработка изображения
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🔍 Scanning your image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
