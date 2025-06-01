import discord
import os
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)

# Получаем ключи из переменных окружения Render
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# Настройка LangChain
llm = ChatOpenAI(temperature=0.7, openai_api_key=OPENAI_API_KEY)
memory = ConversationBufferMemory()
conversation = ConversationChain(llm=llm, memory=memory)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user in message.mentions:
        user_message = message.content.replace(f"<@{client.user.id}>", "").strip()
        reply = conversation.run(user_message)
        await message.channel.send(reply)

client.run(DISCORD_BOT_TOKEN)
