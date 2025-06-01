import discord
from discord.ext import commands
import requests
from PIL import Image
from io import BytesIO
import pytesseract
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    # Игнорировать сообщения от самого бота
    if message.author == bot.user:
        return

    # Проверка на прикреплённые изображения
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🔍 Обрабатываю изображение, подожди секунду...")
                response = requests.get(attachment.url)
                img = Image.open(BytesIO(response.content))
                text = pytesseract.image_to_string(img)
                if text.strip():
                    await message.channel.send(f"📖 Вот что я вижу:\n```{text[:1000]}```")
                else:
                    await message.channel.send("😕 Я не смог распознать текст на этом изображении.")

    # Даем возможность другим командам работать
    await bot.process_commands(message)

@bot.command()
async def hello(ctx):
    await ctx.send("Hi! I'm your English mentor bot 🤖. You can talk to me!")

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
