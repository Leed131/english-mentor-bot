import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def hello(ctx):
    await ctx.send("Hello! I'm your English mentor рџ¤–")

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
