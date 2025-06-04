import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Correct the grammar and improve clarity, but do not explain."},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content.strip()

async def explain_correction(original_text, corrected_text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Explain the grammatical changes made to the sentence."},
            {"role": "user", "content": f"The original sentence was: \"{original_text}\"\nThe corrected version is: \"{corrected_text}\"\nPlease explain why this correction was made."}
        ]
    )
    return response.choices[0].message.content.strip()
