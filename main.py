client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# LangChain setup (memory-enabled chatbot)
template = """You are an English learning assistant. Have a conversation.
{history}
Human: {input}
EnglishMentorBot:"""

prompt = PromptTemplate(input_variables=["history", "input"], template=template)
memory = ConversationBufferMemory()
conversation = ConversationChain(
    llm=ChatOpenAI(model_name="gpt-4o", temperature=0.6),
    memory=memory,
    prompt=prompt
)

# Log when ready
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# GPT-4o Vision: read text from image
async def recognize_text_from_image(url):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": "Extract all readable text from this image."}
                ]
            }
        ],
        max_tokens=1000
    )
    return response.choices[0].message.content.strip()

# Handle image messages
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Image 
