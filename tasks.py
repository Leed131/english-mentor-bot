from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_exercises(prompt):
    instruction = f"Create an English grammar or vocabulary exercise based on the following topic or text:\n{prompt}"
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": instruction}],
        max_tokens=1000
    )
    return response.choices[0].message.content.strip()
