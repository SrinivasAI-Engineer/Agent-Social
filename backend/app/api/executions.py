from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from langgraph.types import Command

from app.api.schemas import CreateExecutionRequest, ExecutionStateResponse, ExecutionSummary, HitlActionsRequest
from app.db import (
    compute_idempotency_key,
    create_execution,
    find_execution_by_idempotency,
    get_execution,
    list_inbox,
    save_execution_state,
)
from app.graph import build_graph, get_interrupt_payload
from app.state import now_iso

router = APIRouter(prefix="/v1", tags=["executions"])

graph = build_graph()


def _status_from_interrupt(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "running"
    if payload.get("type") == "reauth_required":
        return "awaiting_auth"
    return "awaiting_human"


@router.post("/executions", response_model=ExecutionStateResponse)
async def create_execution_endpoint(req: CreateExecutionRequest):
    idem = compute_idempotency_key(req.user_id, req.url)
    existing = find_execution_by_idempotency(req.user_id, idem)
    if existing and existing.status in {"running", "awaiting_human", "awaiting_auth"}:
        state = json.loads(existing.state_json or "{}")
        return ExecutionStateResponse(execution_id=existing.execution_id, status=existing.status, state=state)

    execution_id = uuid.uuid4().hex
    initial_state: dict[str, Any] = {
        "user_id": req.user_id,
        "url": req.url,
        "execution_id": execution_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "terminated": False,
        "terminate_reason": "",
        "publish_status": {"twitter": "not_started", "linkedin": "not_started"},
    }

    create_execution(execution_id, req.user_id, req.url, initial_state, idem)

    result = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": execution_id}})
    payload = get_interrupt_payload(result)
    status = _status_from_interrupt(payload)
    if result.get("terminated"):
        status = "terminated"
    elif not payload:
        status = "completed"
    save_execution_state(execution_id, result, status=status)

    return ExecutionStateResponse(execution_id=execution_id, status=status, state=result)


@router.get("/inbox", response_model=list[ExecutionSummary])
async def inbox():
    rows = list_inbox(["awaiting_human", "awaiting_auth"])
    out: list[ExecutionSummary] = []
    for r in rows:
        state = json.loads(r.state_json or "{}")
        payload = get_interrupt_payload(state) or None
        out.append(
            ExecutionSummary(
                execution_id=r.execution_id,
                user_id=r.user_id,
                url=r.url,
                status=r.status,
                updated_at=r.updated_at.replace(microsecond=0).isoformat() + "Z",
                interrupt=payload,
            )
        )
    return out


@router.get("/executions/{execution_id}", response_model=ExecutionStateResponse)
async def get_execution_state(execution_id: str):
    try:
        ex = get_execution(execution_id)
        state = json.loads(ex.state_json or "{}")
        return ExecutionStateResponse(execution_id=execution_id, status=ex.status, state=state)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/executions/{execution_id}/actions", response_model=ExecutionStateResponse)
async def submit_actions(execution_id: str, req: HitlActionsRequest):
    ex = get_execution(execution_id)
    state = json.loads(ex.state_json or "{}")

    # Resume the graph with the HITL payload.
    result = await graph.ainvoke(Command(resume=req.model_dump()), config={"configurable": {"thread_id": execution_id}})
    payload = get_interrupt_payload(result)
    status = _status_from_interrupt(payload)
    if result.get("terminated"):
        status = "terminated"
    elif not payload:
        status = "completed"

    save_execution_state(execution_id, result, status=status)
    return ExecutionStateResponse(execution_id=execution_id, status=status, state=result)

