import os
import discord
from discord.ext import commands
from openai import OpenAI
from vision import recognize_text_from_image
from speech import transcribe_audio, generate_speech
from grammar import correct_grammar, explain_correction_audio
from memory import log_interaction
from tasks import generate_exercise_from_topic, generate_exercise_from_sample

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
                await message.channel.send(f"📖 I found this:
```{result[:1900]}```")
                log_interaction(user_id, "image_text", result)
            except Exception as e:
                await message.channel.send(f"⚠️ Error reading image: {e}")

        elif filename.endswith(SUPPORTED_AUDIO):
            await message.channel.send("🎙️ Transcribing audio...")
            try:
                text = await transcribe_audio(attachment.url)
                await message.channel.send(f"📝 Transcription:
{text}")

                reply = await correct_grammar(text)
                audio_path = await generate_speech(reply)
                await message.channel.send(f"💬 {reply}")
                await message.channel.send(file=discord.File(audio_path, filename="response.mp3"))
                log_interaction(user_id, "audio_reply", reply)
            except Exception as e:
                await message.channel.send(f"⚠️ Error processing audio: {e}")

    if message.content:
        user_input = message.content.strip().lower()

        if user_input.startswith("почему") or "explain" in user_input:
            explanation_audio_path = await explain_correction_audio(message.content)
            await message.channel.send("🔍 Here's the explanation:")
            await message.channel.send(file=discord.File(explanation_audio_path, filename="explanation.mp3"))

        elif user_input.startswith("создай упражнение") or "exercise on" in user_input:
            topic = message.content.split(" ", 2)[-1]
            exercise = await generate_exercise_from_topic(topic)
            await message.channel.send(f"🧩 Exercise:
```{exercise[:1900]}```")
            log_interaction(user_id, "exercise_topic", topic)

        elif user_input.startswith("пример") or "example" in user_input:
            exercise = await generate_exercise_from_sample(message.content)
            await message.channel.send(f"🧠 Based on your example:
```{exercise[:1900]}```")
            log_interaction(user_id, "exercise_example", message.content)

        else:
            corrected = await correct_grammar(message.content)
            await message.channel.send(f"✅ Corrected:
```{corrected}```")
            log_interaction(user_id, "text_correction", corrected)

    await bot.process_commands(message)

bot.run(TOKEN)
