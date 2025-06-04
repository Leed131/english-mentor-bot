from openai import OpenAI

client = OpenAI()

async def recognize_text_from_image(url):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": "Extract all readable text from this image."}
                ]
            }
        ],
        max_tokens=1000,
    )
    return response.choices[0].message.content.strip()
