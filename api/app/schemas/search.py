"""Schemas for the message search endpoint."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageSearchHit(BaseModel):
    """Single search result — one message that matched the query."""

    model_config = ConfigDict(from_attributes=True)

    message_id: uuid.UUID
    session_id: uuid.UUID
    session_title: str | None
    agent_id: uuid.UUID
    agent_name: str
    agent_icon: str | None
    sender_type: str
    snippet: str
    created_at: datetime


class MessageSearchResponse(BaseModel):
    """List wrapper for search hits."""

    items: list[MessageSearchHit]
    total: int
