from __future__ import annotations

from urllib.parse import urlparse

from app.state import AgentState, now_iso


def _same_site(article_url: str, image_url: str) -> bool:
    try:
        a = urlparse(article_url)
        i = urlparse(image_url)
        return a.netloc and i.netloc and a.netloc.lower() == i.netloc.lower()
    except Exception:
        return False


async def select_image(state: AgentState) -> AgentState:
    """
    STRICT RULE: choose only from images extracted from the same article/blog.

    We only consider FireCrawl-extracted images. We also prefer same-domain images to
    reduce risk of selecting CDN offsite assets; however if FireCrawl provides CDN
    URLs (different host), we still accept them as "extracted from article" but mark source.
    """
    if state.get("terminated"):
        return state

    scraped = state.get("scraped_content") or {}
    article_url = state.get("url") or scraped.get("url") or ""
    images = scraped.get("images") or []

    chosen = None
    # Prefer explicit "og:image" from metadata if present and also in extracted images
    meta = scraped.get("metadata") or {}
    og = meta.get("og:image") or meta.get("twitter:image") or ""
    if og:
        for im in images:
            src = im.get("src") or im.get("url") or ""
            if src and src == og:
                chosen = im
                break

    if not chosen:
        # Prefer first same-site image with reasonable size hints if provided
        def score(im: dict) -> tuple[int, int]:
            src = str(im.get("src") or im.get("url") or "")
            same = 1 if _same_site(article_url, src) else 0
            w = int(im.get("width") or 0) if str(im.get("width") or "").isdigit() else 0
            h = int(im.get("height") or 0) if str(im.get("height") or "").isdigit() else 0
            return (same, w * h)

        for im in sorted([x for x in images if (x.get("src") or x.get("url"))], key=score, reverse=True):
            chosen = im
            break

    if chosen:
        src = str(chosen.get("src") or chosen.get("url"))
        caption = str(chosen.get("alt") or chosen.get("caption") or "")
        state["image_metadata"] = {"image_url": src, "caption": caption, "source": "firecrawl"}
    else:
        # No image found; that's OK.
        state["image_metadata"] = {}

    state["updated_at"] = now_iso()
    return state

