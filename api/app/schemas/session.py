from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """Empty for now — participants/teams are being re-introduced with RBAC."""
    pass


class SessionResponse(BaseModel):
    id: str
    agent_id: str | None = None
    created_by: str
    title: str | None = None
    status: str
    last_message_at: datetime | None = None
    created_at: datetime
    workflow_run_id: str | None = None
    node_id: str | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_session(cls, session) -> "SessionResponse":
        return cls(
            id=str(session.id),
            agent_id=str(session.agent_id) if session.agent_id else None,
            created_by=str(session.created_by),
            title=session.title,
            status=session.status,
            last_message_at=session.last_message_at,
            created_at=session.created_at,
            workflow_run_id=str(session.workflow_run_id) if session.workflow_run_id else None,
            node_id=session.node_id,
        )


class SessionListResponse(BaseModel):
    items: list[SessionResponse]


class MessageResponse(BaseModel):
    id: str
    session_id: str
    sender_type: str
    sender_id: str | None = None
    content: str
    metadata: dict = {}
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_message(cls, msg) -> "MessageResponse":
        return cls(
            id=str(msg.id),
            session_id=str(msg.session_id),
            sender_type=msg.sender_type,
            sender_id=str(msg.sender_id) if msg.sender_id else None,
            content=msg.content,
            metadata=msg.metadata_json,
            created_at=msg.created_at,
        )


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    messages: list[MessageResponse]
    has_more: bool = False


class MessagePageResponse(BaseModel):
    messages: list[MessageResponse]
    has_more: bool = False


class SessionSearchMatch(BaseModel):
    message_id: str
    target_id: str


class SessionSearchResponse(BaseModel):
    matches: list[SessionSearchMatch]


class SessionTitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
