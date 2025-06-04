import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an English teacher. Correct the grammar of the student's message. Return only the corrected version."},
            {"role": "user", "content": text}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content.strip()

async def explain_correction(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an English teacher. Explain the grammar correction in detail in clear terms."},
            {"role": "user", "content": text}
        ],
        max_tokens=700
    )
    return response.choices[0].message.content.strip()
