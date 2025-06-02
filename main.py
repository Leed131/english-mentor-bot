import os
import discord
from discord.ext import commands
from openai import OpenAI

# Инициализация клиента OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Инициализация Discord-бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.command()
async def hello(ctx):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": "Hello, world!"}
        ]
    )
    await ctx.send(response.choices[0].message.content.strip())

bot.run(os.getenv("DISCORD_TOKEN"))
