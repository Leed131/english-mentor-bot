import base64
import mimetypes
import os
from pathlib import Path

from openai import AsyncOpenAI


_client: AsyncOpenAI | None = None
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


def _vision_model() -> str:
    """Use a dedicated stronger model for images unless explicitly overridden."""
    return os.getenv("OPENAI_VISION_MODEL") or "gpt-4o"


VISION_SYSTEM_PROMPT = """
You are a careful vision assistant for language-learning material.
Actually inspect the attached image before answering. Read headings, tables,
examples, handwritten notes, and small printed text when they are legible.
If the image clearly contains a topic, do not ask the user which topic they
mean. Identify the topic from the image and answer the request directly.
If some text is too blurry to read reliably, say which part is unclear instead
of inventing text.
""".strip()


async def recognize_text_from_image(url: str) -> str:
    """Extract readable text from an image URL for the existing Discord flow."""
    response = await _get_client().chat.completions.create(
        model=_vision_model(),
        messages=[
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": url, "detail": "high"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract all readable text from this image faithfully. "
                            "Preserve headings and examples where possible."
                        ),
                    },
                ],
            },
        ],
        max_tokens=1600,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI vision returned an empty response")
    return content.strip()


async def analyze_image_file(
    path: str,
    instruction: str | None = None,
) -> str:
    """Analyze a local JPG/PNG/WEBP image using a vision-capable OpenAI model."""
    image_path = Path(path)
    if not image_path.is_file():
        raise FileNotFoundError(path)

    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
        raise ValueError(f"Unsupported image type: {mime_type}")

    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"

    user_instruction = (instruction or "").strip()
    if not user_instruction:
        user_instruction = (
            "Analyze the image as Danish learning material. Identify the exact "
            "topic from the visible text, explain the important points, and give "
            "a few clear Danish examples."
        )

    response = await _get_client().chat.completions.create(
        model=_vision_model(),
        messages=[
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                    {
                        "type": "text",
                        "text": user_instruction,
                    },
                ],
            },
        ],
        max_tokens=2200,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI vision returned an empty response")
    return content.strip()
