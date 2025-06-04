from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": f"Correct this sentence and return only the corrected version:\n{text}"}
        ]
    )
    return response.choices[0].message.content.strip()

async def explain_correction(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": f"Explain why the following sentence needs correction, or say it's fine:\n{text}"}
        ]
    )
