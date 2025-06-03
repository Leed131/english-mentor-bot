from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def improve_style(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an assistant that improves the style, clarity, and logic of English sentences. "
                    "Keep the meaning, but make it sound natural and expressive. Respond only with the improved version."
                )
            },
            {
                "role": "user",
                "content": text
            }
        ]
    )
    return response.choices[0].message.content.strip()
