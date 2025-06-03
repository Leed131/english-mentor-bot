from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": f"Correct the grammar of the following:\n{text}"}
        ]
    )
    return response.choices[0].message.content.strip()

async def improve_style(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": f"Improve the style of this sentence:\n{text}"}
        ]
    )
    return response.choices[0].message.content.strip()

async def explain_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": f"Explain the grammar in this sentence:\n{text}"}
        ]
    )
    return response.choices[0].message.content.strip()
