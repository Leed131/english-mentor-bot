import os
import discord
from discord.ext import commands
from openai import OpenAI
from vision import recognize_text_from_image
from speech import transcribe_audio, generate_speech
from grammar import correct_grammar, explain_correction
from tasks import generate_task
from memory import log_interaction
from llm_chain import run_chain

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TOKEN = os.getenv("DISCORD_TOKEN")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    user_id = str(message.author.id)
    content = message.content.lower()
    SUPPORTED_IMAGES = (".png", ".jpg", ".jpeg")
    SUPPORTED_AUDIO = (".mp3", ".wav", ".m4a", ".ogg")

    for attachment in message.attachments:
        filename = attachment.filename.lower()

        if filename.endswith(SUPPORTED_IMAGES):
            await message.channel.send("🟨 Processing image...")
            try:
                result = await recognize_text_from_image(attachment.url)
                await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                log_interaction(user_id, "image_text", result)
            except Exception as e:
                await message.channel.send(f"⚠️ Image error: {e}")

        elif filename.endswith(SUPPORTED_AUDIO):
            await message.channel.send("🎙️ Transcribing audio...")
            try:
                text = await transcribe_audio(attachment.url)
                await message.channel.send(f"📝 Transcription:\n{text}")
                reply = run_chain(text)
                audio = await generate_speech(reply)
                await message.channel.send(f"💬 {reply}")
                await message.channel.send(file=discord.File(audio, filename="response.mp3"))
                log_interaction(user_id, "audio_reply", reply)
            except Exception as e:
                await message.channel.send(f"⚠️ Audio error: {e}")

    if message.content:
        # 🔍 Генерация упражнения по запросу
        if content.startswith("exercise") or "упражнение" in content:
            try:
                task = generate_task(message.content)
                await message.channel.send(f"🧩 Here's an exercise:\n{task}")
                log_interaction(user_id, "task", task)
            except Exception as e:
                await message.channel.send(f"⚠️ Task error: {e}")
            return

        try:
            corrected = correct_grammar(message.content)
            await message.channel.send(f"✅ Corrected:\n```{corrected}```")

            if "explain" in content or "почему" in content or "explanation" in content:
                explanation = explain_correction(message.content, corrected)
                await message.channel.send(f"📘 Explanation:\n{explanation}")

            log_interaction(user_id, "text_correction", corrected)
        except Exception as e:
            await message.channel.send(f"⚠️ Grammar error: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
