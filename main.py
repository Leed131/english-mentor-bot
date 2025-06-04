import os
import discord
from discord.ext import commands
from openai import OpenAI
from vision import recognize_text_from_image
from speech import transcribe_audio, generate_speech
from grammar import correct_grammar
from tasks import generate_task
from memory import log_interaction
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
from langchain_core.prompts import PromptTemplate

# Инициализация
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
TOKEN = os.getenv("DISCORD_TOKEN")

# Создание памяти и цепочки LangChain
memory = ConversationBufferMemory(return_messages=True)
conversation_chain = ConversationChain(llm=llm, memory=memory)

# Настройка Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

SUPPORTED_AUDIO = (".mp3", ".wav", ".m4a", ".ogg")
SUPPORTED_IMAGES = (".jpg", ".jpeg", ".png")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# ⛓️ Диалог с ботом через LangChain
async def chat_with_bot(message_text: str) -> str:
    reply = conversation_chain.run(message_text)
    return reply

# 📦 Основная логика бота
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
            except Exception as e:
                await message.channel.send(f"⚠️ Error reading image: {e}")

        elif filename.endswith(SUPPORTED_AUDIO):
            await message.channel.send("🎙️ Transcribing audio...")
            try:
                text = await transcribe_audio(attachment.url)
                await message.channel.send(f"📝 Transcription:\n{text}")
                reply = await chat_with_bot(text)
                voice_path = await generate_speech(reply)
                await message.channel.send(f"💬 {reply}")
                await message.channel.send(file=discord.File(voice_path, filename="response.mp3"))
                log_interaction(user_id, "audio_dialogue", reply)
            except Exception as e:
                await message.channel.send(f"⚠️ Audio error: {e}")

    if message.content:
        try:
            if "exercise" in content or "упражнение" in content:
                topic = message.content.replace("exercise", "").replace("упражнение", "").strip()
                task = await generate_task(topic or "grammar")
                await message.channel.send(f"🧩 Exercise:\n{task}")
                log_interaction(user_id, "task", task)
            elif "grammar" in content or "проверь" in content:
                corrected = await correct_grammar(message.content)
                await message.channel.send(f"✅ Corrected:\n```{corrected}```")
                log_interaction(user_id, "grammar", corrected)
            else:
                response = await chat_with_bot(message.content)
                await message.channel.send(f"💬 {response}")
                log_interaction(user_id, "dialogue", response)
        except Exception as e:
            await message.channel.send(f"⚠️ Error: {e}")

    await bot.process_commands(message)

bot.run(TOKEN)
