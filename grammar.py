from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Correct the grammar in this sentence:\n{text}"}]
    )
    return response.choices[0].message.content.strip()

async def explain_correction(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Correct this sentence and explain the grammar rules:\n{text}"}]
    )
    return response.choices[0].message.content.strip()
