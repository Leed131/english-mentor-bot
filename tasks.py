import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_task(topic):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a professional English teacher who creates clear and focused exercises on grammar and vocabulary."},
            {"role": "user", "content": f"Generate an English grammar exercise about: {topic}. Provide instructions and examples."}
        ]
    )
    return response.choices[0].message.content.strip()
