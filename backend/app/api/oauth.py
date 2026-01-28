from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import settings
from app.db import pop_oauth_state, store_oauth_state, upsert_tokens

router = APIRouter(prefix="/v1/oauth", tags=["oauth"])


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge


@router.get("/twitter/start")
async def twitter_start(user_id: str = Query(..., min_length=1)):
    if not settings.twitter_client_id or not settings.twitter_redirect_uri:
        raise HTTPException(status_code=500, detail="Twitter OAuth not configured.")

    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    store_oauth_state(state=state, provider="twitter", user_id=user_id, code_verifier=verifier)

    params = {
        "response_type": "code",
        "client_id": settings.twitter_client_id,
        "redirect_uri": settings.twitter_redirect_uri,
        "scope": "tweet.read tweet.write users.read offline.access",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"https://twitter.com/i/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/twitter/callback")
async def twitter_callback(code: str = Query(...), state: str = Query(...)):
    row = pop_oauth_state(state=state, provider="twitter")
    if not row:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    verifier = row["code_verifier"]
    user_id = row["user_id"]

    token_url = "https://api.twitter.com/2/oauth2/token"
    basic = _b64url(f"{settings.twitter_client_id}:{settings.twitter_client_secret}".encode("utf-8"))
    headers = {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.twitter_redirect_uri,
        "code_verifier": verifier,
        "client_id": settings.twitter_client_id,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(token_url, headers=headers, data=data)
        if r.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Twitter token exchange failed: {r.text}")
        tok = r.json()

        access_token = tok.get("access_token")
        expires_in = int(tok.get("expires_in") or 0)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None

        # Fetch user id for future needs
        twitter_user_id: Optional[str] = None
        if access_token:
            me = await client.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if me.status_code < 400:
                twitter_user_id = (me.json().get("data") or {}).get("id")

    tok["twitter_user_id"] = twitter_user_id
    upsert_tokens(user_id=user_id, provider="twitter", token_payload=tok, expires_at=expires_at)

    return RedirectResponse(f"{settings.frontend_base_url}?oauth=twitter&status=ok")


@router.get("/linkedin/start")
async def linkedin_start(user_id: str = Query(..., min_length=1)):
    if not settings.linkedin_client_id or not settings.linkedin_redirect_uri:
        raise HTTPException(status_code=500, detail="LinkedIn OAuth not configured.")

    state = secrets.token_urlsafe(24)
    store_oauth_state(state=state, provider="linkedin", user_id=user_id, code_verifier="")

    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "scope": "r_liteprofile w_member_social",
        "state": state,
    }
    url = f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/linkedin/callback")
async def linkedin_callback(code: str = Query(...), state: str = Query(...)):
    row = pop_oauth_state(state=state, provider="linkedin")
    if not row:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    user_id = row["user_id"]

    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.linkedin_redirect_uri,
        "client_id": settings.linkedin_client_id,
        "client_secret": settings.linkedin_client_secret,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"LinkedIn token exchange failed: {r.text}")
        tok = r.json()

        access_token = tok.get("access_token")
        expires_in = int(tok.get("expires_in") or 0)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None

        person_urn: Optional[str] = None
        if access_token:
            me = await client.get(
                "https://api.linkedin.com/v2/me",
                headers={"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0"},
            )
            if me.status_code < 400:
                mid = me.json().get("id")
                if mid:
                    person_urn = f"urn:li:person:{mid}"

    tok["person_urn"] = person_urn
    upsert_tokens(user_id=user_id, provider="linkedin", token_payload=tok, expires_at=expires_at)

    return RedirectResponse(f"{settings.frontend_base_url}?oauth=linkedin&status=ok")

