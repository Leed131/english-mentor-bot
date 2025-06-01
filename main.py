import os
import discord
from discord.ext import commands
from langchain_community.chat_models import ChatOpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate

# --- API keys ---
openai_api_key = os.getenv("OPENAI_API_KEY")
discord_token = os.getenv("DISCORD_TOKEN")

# --- LangChain setup ---
llm = ChatOpenAI(openai_api_key=openai_api_key, model_name="gpt-3.5-turbo", temperature=0.7)

template = """You are EnglishBot, a helpful and patient English mentor.

{history}
User: {input}
EnglishBot:"""

prompt = PromptTemplate(input_variables=["history", "input"], template=template)
memory = ConversationBufferMemory()
conversation = ConversationChain(llm=llm, memory=memory, prompt=prompt)

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")

@bot.command()
async def talk(ctx, *, message):
    response = conversation.run(message)
    await ctx.send(response)

# --- Start bot ---
bot.run(discord_token)
