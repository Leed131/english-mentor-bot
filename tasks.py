from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Создание упражнения по теме
async def generate_exercise_from_topic(topic):
    prompt = f"Create a short English grammar exercise on the topic: {topic}. Provide a few example sentences with gaps, then list the correct answers."
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

# По примеру пользователя
async def generate_exercise_from_sample(text):
    prompt = f"Based on this example: \"{text}\", create a similar English grammar exercise. Include gaps and an answer key."
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()
