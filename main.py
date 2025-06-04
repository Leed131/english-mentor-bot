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

    for attachment in message.attachments:
        filename = attachment.filename.lower()

        if filename.endswith((".jpg", ".jpeg", ".png")):
            await message.channel.send("📷 Processing image...")
            text = await recognize_text_from_image(attachment.url)
            await message.channel.send(f"📖 Extracted:\n```{text}```")
            log_interaction(user_id, "image_text", text)

        elif filename.endswith((".mp3", ".wav", ".m4a", ".ogg")):
            await message.channel.send("🎧 Transcribing...")
            transcript = await transcribe_audio(attachment.url)
            await message.channel.send(f"📝 Transcript:\n```{transcript}```")

            reply = await run_chain(transcript)
            speech_path = await generate_speech(reply)

            await message.channel.send(f"💬 {reply}")
            await message.channel.send(file=discord.File(speech_path, filename="response.mp3"))
            log_interaction(user_id, "audio_reply", reply)

    if message.content:
        if message.content.startswith("!task"):
            topic = message.content[len("!task"):].strip()
            task = await generate_task(topic or None)
            await message.channel.send(f"🧩 Task:\n```{task}```")
            log_interaction(user_id, "generated_task", task)

        elif message.content.startswith("!explain"):
            text = message.content[len("!explain"):].strip()
            explanation = await explain_correction(text)
            await message.channel.send(f"🔍 Explanation:\n```{explanation}```")
            log_interaction(user_id, "explanation", explanation)

        else:
            corrected = await correct_grammar(message.content)
            await message.channel.send(f"✅ Corrected:\n```{corrected}```")
            log_interaction(user_id, "text_correction", corrected)

    await bot.process_commands(message)

bot.run(TOKEN)
