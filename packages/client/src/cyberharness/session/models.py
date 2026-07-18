"""Session pydantic v2 models — Message, ModelCall, Session."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """A single conversation turn."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime
    model_id: str | None = Field(default=None, alias="_model")


class ModelCall(BaseModel):
    """Audit log entry for a model call."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    timestamp: datetime


class Session(BaseModel):
    """A conversation session."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    workspace_id: str = "default"
    title: str | None = None
    state: Literal["active", "complete", "abandoned"] = "active"
    messages: list[Message] = Field(default_factory=list)
    model_log: list[ModelCall] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
