from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_exercise(text: str) -> str:
    prompt = f"""
Ты преподаватель английского языка. Создай 1 короткое грамматическое упражнение по следующей теме или примеру:
{text}

Формат:
1. Заголовок упражнения (например: Present Perfect Practice)
2. Инструкция на английском
3. 4-5 предложений с пропусками или для трансформации
4. (если возможно) короткий ответ

Ответ только на английском.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1000
    )

    return response.choices[0].message.content.strip()
