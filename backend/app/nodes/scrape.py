from __future__ import annotations

from app.clients.firecrawl import FireCrawlError, scrape_article
from app.logging import get_logger
from app.state import AgentState, now_iso

logger = get_logger(__name__)


async def scrape_content(state: AgentState) -> AgentState:
    if state.get("terminated"):
        return state

    url = state["url"]
    try:
        data = await scrape_article(url)
    except FireCrawlError as e:
        logger.exception("Scrape failed")
        state["terminated"] = True
        state["terminate_reason"] = f"Scrape failed: {e}"
        state["updated_at"] = now_iso()
        return state

    markdown = (data.get("markdown") or "").strip()
    html = (data.get("html") or "").strip()
    meta = data.get("metadata") or {}
    title = meta.get("title") or meta.get("og:title") or ""
    images = data.get("images") or meta.get("images") or []

    # Heuristic headings list
    headings = []
    for h in (data.get("headings") or []):
        if isinstance(h, str):
            headings.append(h.strip())
        elif isinstance(h, dict) and h.get("text"):
            headings.append(str(h["text"]).strip())

    # Basic article-only guard: must have meaningful text
    text = markdown or html
    if len(text) < 600:
        state["terminated"] = True
        state["terminate_reason"] = "Scraped content too short; likely not an article/blog."
        state["updated_at"] = now_iso()
        return state

    state["scraped_content"] = {
        "title": title,
        "url": url,
        "text": markdown if markdown else html,
        "headings": headings,
        "metadata": meta,
        "images": images,
    }
    state["updated_at"] = now_iso()
    return state

