import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an English grammar expert. Correct the user's text without changing its meaning."},
            {"role": "user", "content": text}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content.strip()
