from __future__ import annotations

from typing import Literal, Optional

from app.llm import SYSTEM_PROMPT, get_llm
from app.state import AgentState, now_iso


def _fallback_twitter(title: str, insights: list[str], url: str) -> str:
    base = title.strip() or "A useful read"
    bullets = " ".join([f"{i+1}) {x}" for i, x in enumerate(insights[:3]) if x])
    draft = f"{base}\n\n{bullets}\n\nRead: {url}\n\n#AI #Tech"
    return draft[:280].rstrip()


def _fallback_linkedin(title: str, insights: list[str], url: str) -> str:
    base = title.strip() or "Key takeaways"
    lines = [base, "", "Highlights:"]
    for x in insights[:5]:
        lines.append(f"- {x}")
    lines += ["", f"Source: {url}"]
    return "\n".join(lines).strip()


async def generate_posts(
    state: AgentState,
    mode: Literal["both", "twitter_only", "linkedin_only"] = "both",
) -> AgentState:
    if state.get("terminated"):
        return state

    scraped = state.get("scraped_content") or {}
    analysis = state.get("analysis_result") or {}
    title = (scraped.get("title") or "").strip()
    url = state.get("url") or scraped.get("url") or ""
    text = (scraped.get("text") or "").strip()
    insights = [str(x) for x in (analysis.get("key_insights") or []) if str(x).strip()]

    llm = get_llm()

    async def gen_twitter() -> str:
        if not llm:
            return _fallback_twitter(title, insights, url)
        prompt = (
            "Write a Twitter/X post (max 280 chars). "
            "Engaging, high-signal, 0-2 hashtags, include the source URL. "
            "No invented facts.\n\n"
            f"TITLE: {title}\n\n"
            f"KEY INSIGHTS: {insights[:6]}\n\n"
            f"ARTICLE:\n{text[:6000]}"
        )
        msg = await llm.ainvoke([SYSTEM_PROMPT, {"role": "user", "content": prompt}])
        s = msg.content if hasattr(msg, "content") else str(msg)
        return s.strip()[:280]

    async def gen_linkedin() -> str:
        if not llm:
            return _fallback_linkedin(title, insights, url)
        prompt = (
            "Write a LinkedIn post. Professional, insight-driven, 900-1600 characters. "
            "Use short paragraphs and bullets. Include the source URL. "
            "No invented facts.\n\n"
            f"TITLE: {title}\n\n"
            f"KEY INSIGHTS: {insights[:8]}\n\n"
            f"ARTICLE:\n{text[:8000]}"
        )
        msg = await llm.ainvoke([SYSTEM_PROMPT, {"role": "user", "content": prompt}])
        s = msg.content if hasattr(msg, "content") else str(msg)
        return s.strip()

    if mode in ("both", "twitter_only"):
        state["twitter_draft"] = await gen_twitter()
    if mode in ("both", "linkedin_only"):
        state["linkedin_draft"] = await gen_linkedin()

    state["updated_at"] = now_iso()
    return state

