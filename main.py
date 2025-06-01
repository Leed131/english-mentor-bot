import discord
from discord.ext import commands
import os
import nest_asyncio

from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain.chains import ConversationChain

# Обработка асинхронности
nest_asyncio.apply()

# Настройки интентов
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Получение токенов из Render secrets
openai_api_key = os.getenv("OPENAI_API_KEY")

# Шаблон для исправлений и ответа
template = """
You are an English tutor bot. The user is practicing English. 
If the user's message has grammatical or vocabulary mistakes, correct them and explain briefly.
Then answer the message in proper English as a conversation.

Correction example:
User: "I can to go" 
Bot: "You should say 'I can go'. 'to' is not needed here."

---

Chat history:
{history}

User: {input}
EnglishMentorBot:"""

# Настройка LangChain
prompt = PromptTemplate(input_variables=["history", "input"], template=template)
memory = ConversationBufferMemory()
llm = ChatOpenAI(temperature=0.6, openai_api_key=openai_api_key)
conversation = ConversationChain(llm=llm, memory=memory, prompt=prompt)

# Команда-приветствие
@bot.command()
async def hello(ctx):
    await ctx.send("Hi! I'm your English mentor bot 🤖. You can talk to me!")

# Основной диалог — обычные сообщения
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.content.startswith("!"):  # обрабатываем команды отдельно
        await bot.process_commands(message)
        return

    response = conversation.run(message.content)
    await message.channel.send(response)

# Запуск
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
