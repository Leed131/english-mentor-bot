from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Correct the grammar in this text:\n{text}"}],
        max_tokens=500
    )
    return response.choices[0].message.content.strip()

async def explain_correction(original, corrected):
    if original.strip() == corrected.strip():
        return None
    prompt = f"Original: {original}\nCorrected: {corrected}\nExplain the grammar changes in simple terms."
    response = client.chat.completions.
