from memory import log_interaction
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def correct_grammar(user_id, text):
    prompt = f"Check the grammar and suggest corrections for the following sentence:\n\n{text}\n\nAlso briefly explain the corrections if needed."
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    correction = response.choices[0].message.content.strip()

    # Логируем исходный текст и исправление
    log_interaction(user_id, "grammar_check", {
        "input": text,
        "correction": correction
    })

    return correction
