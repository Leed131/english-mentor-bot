import os
import discord
from discord.ext import commands
from openai import OpenAI
from vision import recognize_text_from_image
from speech import transcribe_audio, generate_speech
from grammar import correct_grammar, explain_correction
from memory import log_interaction
from tasks import generate_task

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    attachments = message.attachments
    content = message.content.lower()

    if attachments:
        for attachment in attachments:
            if attachment.filename.lower().endswith((".jpg", ".jpeg", ".png")):
                await message.channel.send("🖼️ Processing image...")
                try:
                    result = await recognize_text_from_image(attachment.url)
                    await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                    log_interaction(user_id, "image_text", result)
                except Exception as e:
                    await message.channel.send(f"⚠️ Error reading image: {e}")

            elif attachment.filename.lower().endswith((".mp3", ".wav", ".m4a", ".ogg")):
                await message.channel.send("🎙️ Transcribing audio...")
                try:
                    text = await transcribe_audio(attachment.url)
                    await message.channel.send(f"📝 Transcription:\n{text}")
                    correction = await correct_grammar(text)
                    await message.channel.send(f"✅ Corrected:\n```{correction}```")
                    audio_path = await generate_speech(correction)
                    await message.channel.send(file=discord.File(audio_path, filename="response.mp3"))
                    log_interaction(user_id, "audio_reply", correction)
                except Exception as e:
                    await message.channel.send(f"⚠️ Error processing audio: {e}")

    elif content.startswith("почему") or content.startswith("why"):
        try:
            explanation = await explain_correction(content)
            await message.channel.send(f"📘 Explanation:\n{explanation}")
        except Exception as e:
            await message.channel.send(f"⚠️ Explanation error: {e}")

    elif "упражнение" in content or "exercise" in content:
        try:
            task = await generate_task(content)
            await message.channel.send(f"📝 Exercise:\n{task}")
        except Exception as e:
            await message.channel.send(f"⚠️ Task error: {e}")

    elif content:
        try:
            corrected = await correct_grammar(content)
            await message.channel.send(f"✅ Corrected:\n```{corrected}```")
            log_interaction(user_id, "text_correction", corrected)
        except Exception as e:
            await message.channel.send(f"⚠️ Text error: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
