from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def run_chain(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


⸻

📄 grammar.py

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


⸻

📄 style.py

from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def improve_style(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Improve the style of the following sentence:\n{text}"}]
    )
    return response.choices[0].message.content.strip()
