import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are an English teacher. Correct any grammar mistakes in the user's sentence. Be polite and helpful."
            },
            {
                "role": "user",
                "content": f"Please correct this sentence:\n{text}"
            }
        ],
        max_tokens=300
    )
    return response.choices[0].message.content.strip()
