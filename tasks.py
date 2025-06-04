from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_task(topic):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": f"Create a short English grammar exercise on the topic: {topic}"}
        ]
    )
    return response.choices[0].message.content.strip()
