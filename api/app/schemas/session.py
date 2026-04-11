from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    type: str = Field("private", pattern="^(private|team)$")
    team_id: str | None = None


class SessionResponse(BaseModel):
    id: str
    agent_id: str
    type: str
    created_by: str
    team_id: str | None = None
    title: str | None = None
    status: str
    pod_name: str | None = None
    last_message_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_session(cls, session) -> "SessionResponse":
        return cls(
            id=str(session.id),
            agent_id=str(session.agent_id),
            type=session.type,
            created_by=str(session.created_by),
            team_id=str(session.team_id) if session.team_id else None,
            title=session.title,
            status=session.status,
            pod_name=session.pod_name,
            last_message_at=session.last_message_at,
            created_at=session.created_at,
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
    """One block-level match from in-chat search.

    `target_id` matches the `data-search-target` attribute the frontend
    paints on the corresponding bubble (text bubble, tool card,
    thinking chip, or the synthetic `{msgId}/user` / `{msgId}/body`
    pseudo-targets for legacy plain content).
    """
    message_id: str
    target_id: str


class SessionSearchResponse(BaseModel):
    """Block-level matches latest-first, top-to-bottom within a message.
    Capped server-side; the cap is high enough that realistic Aviary
    sessions never hit it."""
    matches: list[SessionSearchMatch]


class SessionTitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class InviteRequest(BaseModel):
    email: str
