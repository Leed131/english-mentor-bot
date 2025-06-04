import os
import discord
from discord.ext import commands
from openai import OpenAI
from vision import recognize_text_from_image
from speech import transcribe_audio, generate_speech
from grammar import correct_grammar, explain_correction
from memory import log_interaction
from tasks import generate_task
import tempfile

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
                await message.channel.send(f"📄 I found this:\n```{result[:1900]}```")
                log_interaction(user_id, "image_text", result)
            except Exception as e:
                await message.channel.send(f"⚠️ Error reading image: {e}")

        elif filename.endswith(SUPPORTED_AUDIO):
            await message.channel.send("🎧 Transcribing audio...")
            try:
                text = await transcribe_audio(attachment.url)
                await message.channel.send(f"📝 Transcription:\n{text}")

                corrected = await correct_grammar(text)
                explanation = await explain_correction(text, corrected)
                speech_path = await generate_speech(corrected)

                await message.channel.send(f"✅ Corrected:\n```{corrected}```")
                await message.channel.send(f"🧠 Explanation:\n{explanation}")
                await message.channel.send(file=discord.File(speech_path, filename="response.mp3"))
                log_interaction(user_id, "audio_reply", corrected)
            except Exception as e:
                await message.channel.send(f"⚠️ Error processing audio: {e}")

    if message.content:
        content = message.content.lower()

        # Грамматика
        corrected = await correct_grammar(message.content)
        await message.channel.send(f"✅ Corrected:\n```{corrected}```")
        log_interaction(user_id, "text_correction", corrected)

        if "explain" in content or "почему" in content:
            explanation = await explain_correction(message.content, corrected)
            await message.channel.send(f"🧠 Explanation:\n{explanation}")

        # Генерация упражнений
        if content.startswith("exercise") or "упражнение" in content:
            try:
                task = await generate_task(message.content)
                await message.channel.send(f"📝 Exercise:\n{task}")
                log_interaction(user_id, "exercise", task)
            except Exception as e:
                await message.channel.send(f"⚠️ Error generating exercise: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
