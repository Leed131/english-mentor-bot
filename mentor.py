import asyncio
import os
from typing import Final

from openai import AsyncOpenAI

DEFAULT_MODEL: Final = "gpt-4o-mini"
MAX_HISTORY_MESSAGES: Final = 20

ENGLISH_TUTOR_PROMPT: Final = """
You are an English language tutor. Communicate primarily in English.
Correct mistakes gently and briefly, show a more natural version when useful,
and adapt the difficulty to the learner. Help with conversation, grammar,
vocabulary, translation, and short exercises. Keep answers concise unless the
learner asks for a detailed explanation.
""".strip()

DANISH_TUTOR_PROMPT: Final = """
You are a Danish language tutor. Your primary response language is Danish.
Always answer in Danish when the learner writes or speaks Danish, and continue
the conversation naturally in Danish. Do not switch to English unless the
learner explicitly asks for English.

Correct important mistakes gently and briefly. When useful, show a more natural
Danish version of the learner's phrase. Keep ordinary conversation concise and
do not turn every message into a long lesson. Adapt vocabulary and grammar to
the learner's level.

You may use Russian only when the learner explicitly asks in Russian for an
explanation, or when a difficult grammar point genuinely needs a short Russian
explanation. Help with Danish conversation, pronunciation practice, grammar,
vocabulary, Russian-Danish translation, and short exercises.
""".strip()


class LanguageMentor:
    def __init__(self, platform: str, system_prompt: str) -> None:
        self.platform = platform
        self.system_prompt = system_prompt
        self._histories: dict[str, list[dict[str, str]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._client: AsyncOpenAI | None = None

    def history_key(self, user_id: str | int) -> str:
        return f"{self.platform}:{user_id}"

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is not set")
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client

    async def reply(
        self,
        user_id: str | int,
        text: str,
        learner_context: str | None = None,
    ) -> str:
        key = self.history_key(user_id)
        lock = self._locks.setdefault(key, asyncio.Lock())

        async with lock:
            history = self._histories.setdefault(key, [])
            user_message = {"role": "user", "content": text}

            system_messages = [{"role": "system", "content": self.system_prompt}]
            if learner_context:
                system_messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Use this compact, database-backed learner context when it "
                            "is relevant. Do not claim that an exercise was completed or "
                            "change progress yourself:\n"
                            f"{learner_context}"
                        ),
                    }
                )

            response = await self._get_client().chat.completions.create(
                model=os.getenv("OPENAI_MODEL") or DEFAULT_MODEL,
                temperature=0.7,
                messages=[
                    *system_messages,
                    *history,
                    user_message,
                ],
            )

            answer = response.choices[0].message.content
            if not answer:
                raise RuntimeError("OpenAI returned an empty response")

            history.extend(
                [
                    user_message,
                    {"role": "assistant", "content": answer},
                ]
            )
            if len(history) > MAX_HISTORY_MESSAGES:
                del history[:-MAX_HISTORY_MESSAGES]

            return answer.strip()
