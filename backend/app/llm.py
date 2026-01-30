from __future__ import annotations

from typing import Optional

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings


def get_llm() -> Optional[ChatOpenAI]:
    """
    Returns an LLM client if configured. If not configured, nodes should fall back to
    simple templated generation (still testable, but lower quality).
    """
    if not settings.openai_api_key:
        return None
    return ChatOpenAI(api_key=settings.openai_api_key, model=settings.openai_model, temperature=0.6)


SYSTEM_PROMPT = SystemMessage(
    content=(
        "You are a senior social media copywriter. "
        "Generate platform-specific posts from an article, staying faithful to source. "
        "Do NOT invent facts. Avoid clickbait. Be concise and high-signal."
    )
)

