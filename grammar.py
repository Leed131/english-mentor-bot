from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def correct_grammar(text):
    system_prompt = (
        "You are a helpful assistant that corrects English grammar. "
        "Respond in this format:\n"
        "Corrected: <corrected sentence>\n"
        "Explanation: <why it was corrected, if needed>"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0.5,
    )

    output = response.choices[0].message.content

    if "Explanation:" in output:
        corrected, explanation = output.split("Explanation:", 1)
        return corrected.strip().replace("Corrected:", "").strip(), explanation.strip()
    else:
        return output.strip(), None
