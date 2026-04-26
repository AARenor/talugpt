from __future__ import annotations

from anthropic import Anthropic

from .config import settings


SYSTEM_PROMPT = """You are a concise retrieval assistant.

Answer only from the provided context.
If the context is insufficient, say that clearly.
Do not invent facts, file names, URLs, contact details, or timings.
Keep the answer in the same language as the user.
Finish with a short 'Sources:' line naming the files you used.
"""


def answer_question(query: str, context: str) -> str:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.answer_max_tokens,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": context,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": query},
                ],
            }
        ],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()

