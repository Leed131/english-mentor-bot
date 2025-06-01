import os
import discord
from discord.ext import commands
import nest_asyncio
nest_asyncio.apply()

from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain.chains import ConversationChain

# Настройка Discord intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Получение ключей из переменных окружения
openai_api_key = os.environ["OPENAI_API_KEY"]
discord_token = os.environ["DISCORD_TOKEN"]

# Шаблон общения
template = """
You are an English mentor. Always reply in English, clearly and helpfully.
Chat history:
{history}
User: {input}
EnglishMentorBot:"""

# Настройка LangChain
prompt = PromptTemplate(input_variables=["history", "input"], template=template)
memory = ConversationBufferMemory()
llm = ChatOpenAI(openai_api_key=openai_api_key, temperature=0.6)

conversation = ConversationChain(llm=llm, memory=memory, prompt=prompt)

# Команда приветствия
@bot.command()
async def hello(ctx):
    await ctx.send("Hi! I'm your English mentor bot 🤖. You can talk to me!")

# Основная команда общения
@bot.command()
async def ask(ctx, *, message: str):
    response = conversation.run(message)
    await ctx.send(response)

# Запуск бота
bot.run(discord_token)
