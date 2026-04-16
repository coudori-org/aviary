from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.agent import ModelConfig


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    description: str | None = None
    model_config_data: ModelConfig = Field(..., alias="model_config")

    model_config = {"populate_by_name": True}


class WorkflowUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    definition: dict | None = None
    model_config_data: ModelConfig | None = Field(None, alias="model_config")

    model_config = {"populate_by_name": True}


class WorkflowResponse(BaseModel):
    model_config = {"from_attributes": True, "populate_by_name": True}

    id: str
    name: str
    slug: str
    description: str | None = None
    owner_id: str
    definition: dict
    model_config_data: dict = Field(alias="model_config")
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_workflow(cls, workflow) -> "WorkflowResponse":
        return cls(
            id=str(workflow.id),
            name=workflow.name,
            slug=workflow.slug,
            description=workflow.description,
            owner_id=str(workflow.owner_id),
            definition=workflow.definition,
            model_config=workflow.model_config_json or {},
            status=workflow.status,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )


class WorkflowListResponse(BaseModel):
    items: list[WorkflowResponse]
    total: int
