import os

import discord
from discord.ext import commands

from grammar import correct_grammar
from memory import log_interaction
from mentor import ENGLISH_TUTOR_PROMPT, LanguageMentor
from speech import generate_speech, transcribe_audio
from tasks import generate_task
from vision import recognize_text_from_image


discord_mentor = LanguageMentor("discord", ENGLISH_TUTOR_PROMPT)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

SUPPORTED_AUDIO = (".mp3", ".wav", ".m4a", ".ogg")
SUPPORTED_IMAGES = (".jpg", ".jpeg", ".png")


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}", flush=True)


async def chat_with_bot(text: str, user_id: str) -> str:
    return await discord_mentor.reply(user_id, text)


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    user_id = str(message.author.id)
    content = message.content.lower()

    for attachment in message.attachments:
        filename = attachment.filename.lower()

        if filename.endswith(SUPPORTED_IMAGES):
            await message.channel.send("🖼️ Processing image...")
            try:
                result = await recognize_text_from_image(attachment.url)
                await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                log_interaction(user_id, "image_text", result)
            except Exception as error:
                await message.channel.send(f"⚠️ Error reading image: {error}")

        elif filename.endswith(SUPPORTED_AUDIO):
            await message.channel.send("🎙️ Transcribing audio...")
            try:
                text = await transcribe_audio(attachment.url)
                await message.channel.send(f"📝 Transcription:\n{text}")
                reply = await chat_with_bot(text, user_id)
                voice_path = await generate_speech(reply)
                await message.channel.send(f"💬 {reply}")
                await message.channel.send(
                    file=discord.File(voice_path, filename="response.mp3")
                )
                log_interaction(user_id, "audio_dialogue", reply)
            except Exception as error:
                await message.channel.send(f"⚠️ Audio error: {error}")

    if message.content:
        try:
            if "exercise" in content or "упражнение" in content:
                topic = (
                    message.content.replace("exercise", "")
                    .replace("упражнение", "")
                    .strip()
                )
                task = await generate_task(topic or "grammar")
                await message.channel.send(f"🧩 Exercise:\n{task}")
                log_interaction(user_id, "task", task)
            elif "grammar" in content or "проверь" in content:
                corrected = await correct_grammar(message.content)
                await message.channel.send(f"✅ Corrected:\n```{corrected}```")
                log_interaction(user_id, "grammar", corrected)
            else:
                response = await chat_with_bot(message.content, user_id)
                await message.channel.send(f"💬 {response}")
                log_interaction(user_id, "dialogue", response)
        except Exception as error:
            await message.channel.send(f"⚠️ Error: {error}")

    await bot.process_commands(message)


async def run_discord_bot() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")

    print("Discord bot started", flush=True)
    try:
        await bot.start(token)
    finally:
        if not bot.is_closed():
            await bot.close()
