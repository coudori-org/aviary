from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._common import OptionalUuidStr, UuidStr


class SessionCreate(BaseModel):
    pass


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    agent_id: OptionalUuidStr = None
    created_by: UuidStr
    title: str | None = None
    status: str
    last_message_at: datetime | None = None
    created_at: datetime
    workflow_run_id: OptionalUuidStr = None
    node_id: str | None = None


class SessionListResponse(BaseModel):
    items: list[SessionResponse]


class MessageResponse(BaseModel):
    # ORM column is ``metadata_json`` (``metadata`` is a reserved name on
    # SQLAlchemy's Base). Wire contract keeps the shorter ``metadata``.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UuidStr
    session_id: UuidStr
    sender_type: str
    sender_id: OptionalUuidStr = None
    content: str
    metadata: dict = Field(default_factory=dict, validation_alias="metadata_json")
    created_at: datetime


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
