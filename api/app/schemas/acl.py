from datetime import datetime

from pydantic import BaseModel, Field


class ACLCreate(BaseModel):
    user_id: str | None = None
    team_id: str | None = None
    role: str = Field(..., pattern="^(owner|admin|user|viewer)$")


class ACLUpdate(BaseModel):
    role: str = Field(..., pattern="^(owner|admin|user|viewer)$")


class ACLResponse(BaseModel):
    id: str
    agent_id: str
    user_id: str | None = None
    team_id: str | None = None
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_acl(cls, acl) -> "ACLResponse":
        return cls(
            id=str(acl.id),
            agent_id=str(acl.agent_id),
            user_id=str(acl.user_id) if acl.user_id else None,
            team_id=str(acl.team_id) if acl.team_id else None,
            role=acl.role,
            created_at=acl.created_at,
        )


class ACLListResponse(BaseModel):
    items: list[ACLResponse]
