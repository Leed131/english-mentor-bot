from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful English teacher. Correct grammar in a student's sentence."},
            {"role": "user", "content": f"Correct this sentence:\n{text}"}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content.strip()

async def explain_correction(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Explain the grammar correction for a student learning English."},
            {"role": "user", "content": f"Explain this correction:\n{text}"}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content.strip()
