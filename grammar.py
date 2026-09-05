import os

from openai import AsyncOpenAI


client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def correct_grammar(text):
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": f"Correct the grammar and improve clarity: {text}"}
        ]
    )
    return response.choices[0].message.content.strip()
