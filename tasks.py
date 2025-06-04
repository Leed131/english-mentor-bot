import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_task(topic):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You're an experienced English teacher. Generate clear and useful grammar or vocabulary exercises with instructions and examples."},
            {"role": "user", "content": f"Generate an English grammar or vocabulary exercise about: {topic}"}
        ]
    )
    return response.choices[0].message.content.strip()
