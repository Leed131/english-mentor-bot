from openai import OpenAI
import os
import tempfile

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful English grammar corrector. Reply only with the corrected version of the text."},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content.strip()

async def explain_correction(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Correct the grammar and explain the rule in simple English."},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message.content.strip()

async def explain_correction_audio(text):
    explanation = await explain_correction(text)
    speech = client.audio.speech.create(
        model="tts-1-hd",
        voice="alloy",  # британский мужской
        input=explanation
    )
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    with open(temp_file.name, "wb") as f:
        f.write(speech.content)
    return temp_file.name

