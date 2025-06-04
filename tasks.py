from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_task(topic: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an English teacher who creates grammar exercises."},
            {"role": "user", "content": f"Create a grammar exercise on the topic: {topic}"}
        ],
        temperature=0.5
    )
    return response.choices[0].message.content.strip()
