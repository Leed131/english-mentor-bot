import os

from openai import AsyncOpenAI


client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def improve_style(text):
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Improve the style of the following sentence:\n{text}"}]
    )
    return response.choices[0].message.content.strip()
