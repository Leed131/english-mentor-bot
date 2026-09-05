import json
import os
from typing import Any

from openai import AsyncOpenAI


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


def _model() -> str:
    return os.getenv("OPENAI_MODEL") or "gpt-4o-mini"


def _validate_questions(payload: Any, topic: str, count: int) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Quiz payload must be an object")
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        raise ValueError("Quiz payload is missing questions")

    questions: list[dict[str, Any]] = []
    for raw in raw_questions[:count]:
        if not isinstance(raw, dict):
            continue
        question = str(raw.get("question", "")).strip()
        options = raw.get("options")
        explanation = str(raw.get("explanation", "")).strip()
        try:
            correct_index = int(raw.get("correct_index"))
        except (TypeError, ValueError):
            continue

        if not question or not isinstance(options, list):
            continue
        normalized_options = [str(option).strip() for option in options if str(option).strip()]
        if len(normalized_options) not in {3, 4}:
            continue
        if correct_index < 0 or correct_index >= len(normalized_options):
            continue

        correct_answer = normalized_options[correct_index]
        if not explanation:
            explanation = f"Det rigtige svar er: {correct_answer}."
        elif correct_answer.lower() not in explanation.lower():
            explanation = f"Det rigtige svar er: {correct_answer}. {explanation}"

        questions.append(
            {
                "question": question[:500],
                "options": normalized_options,
                "correct_index": correct_index,
                "explanation": explanation[:700],
                "topic": str(raw.get("topic") or topic)[:160],
                "error_type": str(raw.get("error_type") or "grammar")[:80],
                "error_example": str(raw.get("error_example") or question)[:500],
                "error_correction": str(raw.get("error_correction") or correct_answer)[:500],
            }
        )

    if len(questions) < 3:
        raise ValueError("OpenAI returned too few valid quiz questions")
    return questions


async def generate_topic_quiz(
    topic: str,
    learner_context: str,
    *,
    count: int = 5,
) -> list[dict[str, Any]]:
    count = max(3, min(count, 10))
    normalized_topic = topic.strip() or "dansk grammatik"

    prompt = f"""Create {count} short multiple-choice exercises for a learner of Danish.

TOPIC:
{normalized_topic}

LEARNER CONTEXT:
{learner_context or 'Level A1. No other saved context.'}

Return ONLY a JSON object with this exact shape:
{{
  "questions": [
    {{
      "question": "...",
      "options": ["...", "...", "..."],
      "correct_index": 0,
      "explanation": "Short Danish explanation that explicitly includes the correct answer.",
      "topic": "short topic name",
      "error_type": "grammar",
      "error_example": "a typical wrong form",
      "error_correction": "the correct form"
    }}
  ]
}}

Rules:
- Write the exercise text in Danish.
- Use 3 or 4 answer options per question.
- Exactly one option must be correct.
- Questions must test the supplied topic, not generic Danish.
- Mix recognition and sentence-choice questions.
- Keep each question compact enough for Telegram.
- Do not include percentages, scores, markdown, or prose outside JSON.
"""

    response = await _get_client().chat.completions.create(
        model=_model(),
        temperature=0.4,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You create accurate Danish language-learning quizzes as strict JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=2400,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI returned an empty quiz")
    return _validate_questions(json.loads(content), normalized_topic, count)
