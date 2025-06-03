from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an English grammar assistant."},
            {"role": "user", "content": f"Correct this sentence: {text}"}
        ],
        temperature=0.2
    )
    return response.choices[0].message.content.strip()

async def explain_correction(text: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an English teacher who explains grammar corrections clearly."},
            {"role": "user", "content": f"Please explain the grammar of the sentence: {text}"}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()
