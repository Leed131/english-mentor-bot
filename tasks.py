import os

from openai import AsyncOpenAI


client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def generate_task(topic):
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": f"Create a short grammar or vocabulary exercise on the topic: {topic}"}
        ]
    )
    return response.choices[0].message.content.strip()
