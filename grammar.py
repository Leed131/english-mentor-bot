async def correct_grammar(text):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You're an English teacher helping with grammar corrections."
            },
            {
                "role": "user",
                "content": f"Please correct the grammar of the following sentence:\n{text}"
            }
        ],
        max_tokens=500
    )
    return response.choices[0].message.content.strip()
