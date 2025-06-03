from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_exercise(prompt):
    instructions = (
        "Generate a concise English language exercise based on the topic or example provided. "
        "Use clear formatting with numbered questions. Keep it suitable for intermediate to advanced learners."
    )
    full_prompt = f"{instructions}\n\nTopic or sample:\n{prompt}"
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.7
    )
    
    return response.choices[0].message.content.strip()
