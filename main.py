import os
import discord
from discord.ext import commands
from openai import OpenAI
from vision import recognize_text_from_image
from speech import transcribe_audio, generate_speech
from grammar import correct_grammar, explain_correction
from memory import log_interaction

import aiohttp
import tempfile
import requests

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 🔁 Временное хранилище для последних запросов пользователя
memory = {}

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    user_id = str(message.author.id)
    SUPPORTED_AUDIO = (".mp3", ".wav", ".m4a", ".ogg")
    SUPPORTED_IMAGES = (".jpg", ".jpeg", ".png")

    for attachment in message.attachments:
        filename = attachment.filename.lower()

        if filename.endswith(SUPPORTED_IMAGES):
            await message.channel.send("🖼️ Processing image...")
            try:
                result = await recognize_text_from_image(attachment.url)
                await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                log_interaction(user_id, "image_text", result)
            except Exception as e:
                await message.channel.send(f"⚠️ Error reading image: {e}")

        elif filename.endswith(SUPPORTED_AUDIO):
            await message.channel.send("🎙️ Transcribing audio...")
            try:
                text = await transcribe_audio(attachment.url)
                await message.channel.send(f"📝 Transcription:\n{text}")

                memory[user_id] = {"last_input": text}  # сохраняем для explain
                reply = await correct_grammar(text)
                await message.channel.send(f"✅ Corrected:\n```{reply}```")

                speech_path = await generate_speech(reply)
                await message.channel.send(file=discord.File(speech_path, filename="response.mp3"))

                log_interaction(user_id, "audio_reply", reply)
            except Exception as e:
                await message.channel.send(f"⚠️ Error processing audio: {e}")

    # ✅ Коррекция текста
    if message.content:
        content = message.content.strip()

        if content.lower() in ("explain", "поясни"):
            if user_id in memory and "last_input" in memory[user_id]:
                try:
                    explanation = await explain_correction(memory[user_id]["last_input"])
                    await message.channel.send(f"📘 Explanation:\n{explanation}")
                except Exception as e:
                    await message.channel.send(f"⚠️ Error generating explanation: {e}")
            else:
                await message.channel.send("⚠️ No previous sentence found to explain.")
        else:
            memory[user_id] = {"last_input": content}
            try:
                corrected = await correct_grammar(content)
                await message.channel.send(f"✅ Corrected:\n```{corrected}```")
                log_interaction(user_id, "text_correction", corrected)
            except Exception as e:
                await message.channel.send(f"⚠️ Error correcting text: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
