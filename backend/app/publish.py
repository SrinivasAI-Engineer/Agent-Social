from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.db import get_tokens
from app.logging import get_logger
from app.state import AgentState, now_iso

logger = get_logger(__name__)


def _image_is_from_scrape(state: AgentState, url: str) -> bool:
    imgs = (state.get("scraped_content") or {}).get("images") or []
    for im in imgs:
        src = str(im.get("src") or im.get("url") or "")
        if src and src == url:
            return True
    return False


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def _download_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, follow_redirects=True)
        r.raise_for_status()
        return r.content


async def upload_image(state: AgentState) -> AgentState:
    """
    Upload image ONLY after explicit human approval (enforced by routing).
    Attempts Twitter + LinkedIn uploads; failures do not auto-terminate publishing.
    """
    if state.get("terminated"):
        return state

    img = state.get("image_metadata") or {}
    image_url = img.get("image_url") or ""
    if not image_url:
        state.setdefault("media_ids", {})
        state["updated_at"] = now_iso()
        return state

    if not _image_is_from_scrape(state, image_url):
        # Prevent tampering: only allow image URLs that were extracted from the article.
        logger.warning("Blocked image upload: URL not in scraped image set.")
        state.setdefault("media_ids", {})
        state["updated_at"] = now_iso()
        return state

    blob = await _download_bytes(image_url)
    state.setdefault("media_ids", {})

    # Upload to Twitter (best-effort)
    try:
        tw = get_tokens(state["user_id"], "twitter") or {}
        access_token = tw.get("access_token")
        if access_token:
            # Twitter media upload is historically v1.1; many setups accept Bearer user token.
            async with httpx.AsyncClient(timeout=45) as client:
                r = await client.post(
                    "https://upload.twitter.com/1.1/media/upload.json",
                    headers={"Authorization": f"Bearer {access_token}"},
                    files={"media": ("image.jpg", blob)},
                )
                if r.status_code < 400:
                    media_id = str(r.json().get("media_id_string") or r.json().get("media_id") or "")
                    if media_id:
                        state["media_ids"]["twitter_media_id"] = media_id
                else:
                    logger.warning("Twitter image upload failed: %s %s", r.status_code, r.text[:300])
    except Exception:
        logger.exception("Twitter image upload error")

    # Upload to LinkedIn (best-effort; requires person_urn in token payload)
    try:
        li = get_tokens(state["user_id"], "linkedin") or {}
        access_token = li.get("access_token")
        owner = li.get("person_urn")  # e.g. "urn:li:person:xxxx"
        if access_token and owner:
            headers = {"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0"}
            register_body = {
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "owner": owner,
                    "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}],
                }
            }
            async with httpx.AsyncClient(timeout=45) as client:
                reg = await client.post(
                    "https://api.linkedin.com/v2/assets?action=registerUpload",
                    headers=headers | {"Content-Type": "application/json"},
                    json=register_body,
                )
                if reg.status_code >= 400:
                    raise RuntimeError(f"LinkedIn registerUpload failed: {reg.status_code} {reg.text}")
                reg_json = reg.json()
                asset = reg_json.get("value", {}).get("asset")
                upload_url = (
                    (reg_json.get("value", {}).get("uploadMechanism", {}) or {})
                    .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
                    .get("uploadUrl")
                )
                if asset and upload_url:
                    up = await client.put(upload_url, content=blob, headers={"Authorization": f"Bearer {access_token}"})
                    if up.status_code >= 400:
                        raise RuntimeError(f"LinkedIn upload failed: {up.status_code} {up.text}")
                    state["media_ids"]["linkedin_asset_urn"] = str(asset)
    except Exception:
        logger.exception("LinkedIn image upload error")

    state["updated_at"] = now_iso()
    return state


async def publish_twitter(state: AgentState) -> AgentState:
    if state.get("terminated"):
        return state

    state.setdefault("publish_status", {"twitter": "not_started", "linkedin": "not_started"})
    if state["publish_status"].get("twitter") == "published":
        return state

    text = (state.get("approved_twitter_post") or "").strip()
    if not text:
        state["publish_status"]["twitter"] = "skipped"
        state["updated_at"] = now_iso()
        return state

    tw = get_tokens(state["user_id"], "twitter") or {}
    access_token = tw.get("access_token")
    if not access_token:
        state["terminated"] = True
        state["terminate_reason"] = "Missing Twitter access token."
        state["updated_at"] = now_iso()
        return state

    payload: dict[str, Any] = {"text": text}
    media_id = (state.get("media_ids") or {}).get("twitter_media_id")
    if media_id:
        payload["media"] = {"media_ids": [media_id]}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.twitter.com/2/tweets",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json=payload,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"Twitter publish failed: {r.status_code} {r.text}")
            tweet_id = str((r.json().get("data") or {}).get("id") or "")
            state["publish_status"]["twitter"] = "published"
            if tweet_id:
                state["publish_status"]["tweet_id"] = tweet_id
    except Exception as e:
        state["publish_status"]["twitter"] = "failed"
        state["publish_status"]["last_error"] = str(e)
        # Do not auto-terminate; LinkedIn may still proceed.
        logger.exception("Twitter publish error")

    state["updated_at"] = now_iso()
    return state


async def publish_linkedin(state: AgentState) -> AgentState:
    if state.get("terminated"):
        return state

    state.setdefault("publish_status", {"twitter": "not_started", "linkedin": "not_started"})
    if state["publish_status"].get("linkedin") == "published":
        return state

    text = (state.get("approved_linkedin_post") or "").strip()
    if not text:
        state["publish_status"]["linkedin"] = "skipped"
        state["updated_at"] = now_iso()
        return state

    li = get_tokens(state["user_id"], "linkedin") or {}
    access_token = li.get("access_token")
    author = li.get("person_urn")  # "urn:li:person:xxxx"
    if not access_token or not author:
        state["terminated"] = True
        state["terminate_reason"] = "Missing LinkedIn access token or person_urn."
        state["updated_at"] = now_iso()
        return state

    asset = (state.get("media_ids") or {}).get("linkedin_asset_urn")
    share = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "IMAGE" if asset else "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    if asset:
        share["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
            {"status": "READY", "description": {"text": ""}, "media": asset, "title": {"text": ""}}
        ]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.linkedin.com/v2/ugcPosts",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json=share,
            )
            if r.status_code >= 400:
                raise RuntimeError(f"LinkedIn publish failed: {r.status_code} {r.text}")
            post_urn = r.headers.get("x-restli-id") or ""
            state["publish_status"]["linkedin"] = "published"
            if post_urn:
                state["publish_status"]["linkedin_post_urn"] = post_urn
    except Exception as e:
        state["publish_status"]["linkedin"] = "failed"
        state["publish_status"]["last_error"] = str(e)
        logger.exception("LinkedIn publish error")

    state["updated_at"] = now_iso()
    return state

