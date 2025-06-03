import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def improve_style(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Rephrase the user's sentence to make it more natural and fluent, like a native C2 speaker."},
            {"role": "user", "content": text}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content.strip()
