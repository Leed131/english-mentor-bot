from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def improve_style(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Improve the style of the following sentence:\n{text}"}]
    )
    return response.choices[0].message.content.strip()
