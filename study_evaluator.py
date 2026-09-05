import json
import os
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from mentor import DEFAULT_MODEL


@dataclass(frozen=True)
class WritingEvaluation:
    feedback_da: str
    score: int
    grammar_errors: list[dict[str, str]]
    vocabulary_errors: list[dict[str, str]]


def _validated_errors(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    errors: list[dict[str, str]] = []
    for item in value[:10]:
        if not isinstance(item, dict):
            continue
        example = str(item.get("example", "")).strip()
        correction = str(item.get("correction", "")).strip()
        if not example or not correction:
            continue
        errors.append(
            {
                "error_type": str(item.get("error_type", "other"))[:80],
                "example": example[:500],
                "correction": correction[:500],
            }
        )
    return errors


async def evaluate_danish_writing(
    text: str,
    learner_context: str,
) -> WritingEvaluation:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL") or DEFAULT_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Evaluate a short Danish learner text. Return only a JSON object "
                    "with keys feedback_da (short Danish feedback), score (integer "
                    "0-100), grammar_errors, and vocabulary_errors. Each error array "
                    "contains objects with error_type, example, and correction. Do not "
                    "invent errors. The application, not the model, updates progress."
                ),
            },
            {
                "role": "system",
                "content": f"Relevant learner context only:\n{learner_context}",
            },
            {"role": "user", "content": text[:5000]},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI returned an empty writing evaluation")

    payload = json.loads(content)
    feedback = str(payload.get("feedback_da", "")).strip()
    if not feedback:
        raise ValueError("Writing evaluation has no feedback")
    try:
        score = int(payload.get("score", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("Writing evaluation score is invalid") from error

    return WritingEvaluation(
        feedback_da=feedback[:3000],
        score=max(0, min(100, score)),
        grammar_errors=_validated_errors(payload.get("grammar_errors")),
        vocabulary_errors=_validated_errors(payload.get("vocabulary_errors")),
    )
