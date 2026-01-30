from __future__ import annotations

from datetime import datetime, timezone

from langgraph.types import interrupt

from app.db import get_tokens, get_tokens_expiry
from app.state import AgentState, now_iso


def _is_expired(dt: datetime | None) -> bool:
    if dt is None:
        return False
    return dt.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)


async def check_authentication(state: AgentState) -> AgentState:
    """
    Tokens are obtained OUTSIDE LangGraph. Here we only check presence/expiry.
    If missing/expired, we interrupt and require re-auth, then resume.
    """
    if state.get("terminated"):
        return state

    user_id = state.get("user_id") or ""
    if not user_id:
        state["terminated"] = True
        state["terminate_reason"] = "Missing user_id for auth check."
        state["updated_at"] = now_iso()
        return state

    tw = get_tokens(user_id, "twitter")
    li = get_tokens(user_id, "linkedin")
    tw_exp = get_tokens_expiry(user_id, "twitter")
    li_exp = get_tokens_expiry(user_id, "linkedin")
    tw_present = tw is not None
    li_present = li is not None

    needs = []
    if not tw_present or _is_expired(tw_exp):
        needs.append("twitter")
    if not li_present or _is_expired(li_exp):
        needs.append("linkedin")

    state["auth_tokens"] = {
        "twitter_present": tw_present and not _is_expired(tw_exp),
        "twitter_expires_at": tw_exp.isoformat() if tw_exp else None,
        "linkedin_present": li_present and not _is_expired(li_exp),
        "linkedin_expires_at": li_exp.isoformat() if li_exp else None,
    }

    if needs:
        payload = {
            "type": "reauth_required",
            "execution_id": state.get("execution_id"),
            "user_id": user_id,
            "needs": needs,
            "message": "Authentication required before publishing. Complete OAuth, then resume.",
        }
        _ = interrupt(payload)

        # After resume, re-check (state doesn't carry tokens; DB does)
        tw2 = get_tokens(user_id, "twitter")
        li2 = get_tokens(user_id, "linkedin")
        tw_exp2 = get_tokens_expiry(user_id, "twitter")
        li_exp2 = get_tokens_expiry(user_id, "linkedin")
        if tw2 is None or li2 is None or _is_expired(tw_exp2) or _is_expired(li_exp2):
            state["terminated"] = True
            state["terminate_reason"] = "Authentication not completed."

    state["updated_at"] = now_iso()
    return state

