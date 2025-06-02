import os
import discord
from discord.ext import commands
import openai
import aiohttp
import base64

# ⬛️ Настройка ключей
openai.api_key = os.getenv("OPENAI_API_KEY")
TOKEN = os.getenv("DISCORD_TOKEN")

# ⬛️ Настройка бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ⬛️ Стартовое сообщение
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# ⬛️ Распознавание текста на изображении
async def recognize_text_from_image(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            image_bytes = await resp.read()

    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    response = openai.chat.completions.create(
        model="gpt-4-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    { "type": "image_url", "image_url": { "url": url } },
                    { "type": "text", "text": "Please extract all readable text from this image and return it." }
                ]
            }
        ],
        max_tokens=1000
    )
    return response.choices[0].message.content.strip()

# ⬛️ Обработка сообщений и изображений
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Ответ на текст
    if message.content and not message.content.startswith("!"):
        reply = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You're a friendly English mentor. Answer clearly and helpfully."},
                {"role": "user", "content": message.content}
            ]
        )
        await message.channel.send(reply.choices[0].message.content.strip())

    # Ответ на изображение
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🔍 Scanning your image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📖 I found this:\n{result[:1900]}")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
