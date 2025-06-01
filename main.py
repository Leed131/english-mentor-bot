import discord
from discord.ext import commands
import os
import random

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 🧠 Небольшой словарь для примера
vocab = {
    "apple": "яблоко",
    "house": "дом",
    "book": "книга",
    "tree": "дерево",
    "sun": "солнце"
}

# 📝 Сохраняем текущие слова для каждого пользователя
user_quiz = {}

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.command()
async def hello(ctx):
    await ctx.send("👋 Hello! I'm your English mentor bot. Type !help to see what I can do.")

@bot.command()
async def vocab(ctx):
    word, translation = random.choice(list(vocab.items()))
    await ctx.send(f"📘 Word: **{word}**\n📝 Translation: **{translation}**")

@bot.command()
async def quiz(ctx):
    word = random.choice(list(vocab.keys()))
    user_quiz[ctx.author.id] = word
    await ctx.send(f"🔍 Translate this word to Russian: **{word}**")

@bot.command()
async def answer(ctx, *, user_answer):
    word = user_quiz.get(ctx.author.id)
    if not word:
        await ctx.send("⚠️ You haven't started a quiz. Type !quiz first.")
        return
    correct = vocab[word].lower()
    if user_answer.lower().strip() == correct:
        await ctx.send("✅ Correct!")
    else:
        await ctx.send(f"❌ Incorrect. The correct answer is: **{correct}**")
    user_quiz[ctx.author.id] = None

@bot.command()
async def help(ctx):
    await ctx.send("""
🧠 English Mentor Bot Commands:
- !hello — say hello
- !vocab — get a word and its translation
- !quiz — get a word to translate
- !answer [your answer] — answer the quiz
- !help — show this message
""")

# 🔑 Запуск бота
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
