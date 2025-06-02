import os
import discord
from discord.ext import commands
from openai import OpenAI
import aiohttp

# Настройка ключей
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

# Настройка бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# Функция распознавания текста с изображения
async def recognize_text_from_image(url):
    response = client.chat.completions.create(
        model="gpt-4o",
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

# Обработка сообщений
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🔍 Scanning your image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
