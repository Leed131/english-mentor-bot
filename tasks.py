from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_task(topic):
    prompt = f"Generate an English learning exercise on the topic '{topic}' with examples."
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()
