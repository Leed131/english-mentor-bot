import os
import discord
from discord.ext import commands
from openai import OpenAI

from vision import recognize_text_from_image
from speech import transcribe_audio, generate_speech
from grammar import correct_grammar
from style import improve_style
from memory import log_interaction

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

        # Обработка изображений
        if filename.endswith(SUPPORTED_IMAGES):
            await message.channel.send("🖼️ Processing image...")
            try:
                result = await recognize_text_from_image(attachment.url)
                await message.channel.send(f"📖 I found this:\n```{result[:1900]}```")
                log_interaction(user_id, "image_text", result)
            except Exception as e:
                await message.channel.send(f"⚠️ Error reading image: {e}")

        # Обработка аудио
        elif filename.endswith(SUPPORTED_AUDIO):
            await message.channel.send("🎙️ Transcribing audio...")
            try:
                text = await transcribe_audio(attachment.url)
                await message.channel.send(f"📝 Transcription:\n{text}")

                reply = await correct_grammar(text)
                speech_path = await generate_speech(reply)

                await message.channel.send(f"💬 {reply}")
                await message.channel.send(file=discord.File(speech_path, filename="response.mp3"))
                log_interaction(user_id, "audio_reply", reply)
            except Exception as e:
                await message.channel.send(f"⚠️ Error processing audio: {e}")

    # Обработка текстовых сообщений
    if message.content:
        corrected = await correct_grammar(message.content)
        await message.channel.send(f"✅ Corrected:\n```{corrected}```")
        log_interaction(user_id, "text_correction", corrected)

        styled = await improve_style(message.content)
        await message.channel.send(f"🎨 Improved style:\n```{styled}```")
        log_interaction(user_id, "style_improvement", styled)

    await bot.process_commands(message)

bot.run(TOKEN)
