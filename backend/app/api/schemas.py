from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CreateExecutionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=8)


class ExecutionSummary(BaseModel):
    execution_id: str
    user_id: str
    url: str
    status: str
    updated_at: str
    interrupt: Optional[dict[str, Any]] = None


class ExecutionStateResponse(BaseModel):
    execution_id: str
    status: str
    state: dict[str, Any]


class HitlActionsRequest(BaseModel):
    approve_content: Optional[bool] = False
    reject_content: Optional[bool] = False
    approve_image: Optional[bool] = False
    reject_image: Optional[bool] = False
    regenerate_twitter: Optional[bool] = False
    regenerate_linkedin: Optional[bool] = False
    edited_twitter: Optional[str] = ""
    edited_linkedin: Optional[str] = ""

