import os

from openai import AsyncOpenAI


client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def run_chain(prompt):
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()
