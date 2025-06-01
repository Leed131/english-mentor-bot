import openai
import aiohttp
import discord
from discord.ext import commands

# Настройка клиента OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Настройка бота
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

async def recognize_text_from_image(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            image_bytes = await resp.read()

    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": "Read the text from this image and return it as plain text."}
                ]
            }
        ],
        max_tokens=1000
    )
    return response.choices[0].message.content.strip()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith((".png", ".jpg", ".jpeg")):
                await message.channel.send("🔍 Scanning the image...")
                try:
                    text = await recognize_text_from_image(attachment.url)
                    if text:
                        await message.channel.send(f"📖 I found this:\n```{text[:1000]}```")
                    else:
                        await message.channel.send("😕 I couldn't recognize any text.")
                except Exception as e:
                    await message.channel.send(f"❌ Error reading image: {e}")
    
    await bot.process_commands(message)

# Запуск
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
