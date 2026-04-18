import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.schemas.agent import ModelConfig

# Pydantic v2 reserves the ``model_`` prefix; workflow schemas need
# ``model_config_json`` to match the ORM attribute, so every schema that
# touches it turns the protection off.
_MODEL_CONFIG_KEY_ALIAS = {"alias": "model_config"}


def _to_str(v):
    """Accept ORM uuid.UUID values and serialize them as strings —
    wire-level ids stay ``str`` for frontend compatibility."""
    return str(v) if isinstance(v, uuid.UUID) else v


UuidStr = Annotated[str, BeforeValidator(_to_str)]
OptionalUuidStr = Annotated[str | None, BeforeValidator(_to_str)]


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    description: str | None = None
    model_config_json: ModelConfig = Field(..., **_MODEL_CONFIG_KEY_ALIAS)
    runtime_endpoint: str | None = Field(None, max_length=512)


class WorkflowUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    definition: dict | None = None
    model_config_json: ModelConfig | None = Field(None, **_MODEL_CONFIG_KEY_ALIAS)
    runtime_endpoint: str | None = Field(None, max_length=512)


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, protected_namespaces=(),
    )

    id: UuidStr
    name: str
    slug: str
    description: str | None = None
    owner_id: UuidStr
    definition: dict
    model_config_json: dict = Field(**_MODEL_CONFIG_KEY_ALIAS)
    runtime_endpoint: str | None = None
    status: str
    current_version: int | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowListResponse(BaseModel):
    items: list[WorkflowResponse]
    total: int


class WorkflowVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    workflow_id: UuidStr
    version: int
    deployed_by: UuidStr
    deployed_at: datetime
    definition: dict


class WorkflowRunCreate(BaseModel):
    run_type: str = Field(default="deployed", pattern="^(draft|deployed)$")
    trigger_type: str = Field(default="manual", pattern="^(manual|webhook|cron)$")
    trigger_data: dict = Field(default_factory=dict)


class WorkflowNodeRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    node_id: str
    node_type: str
    status: str
    input_data: dict | None = None
    output_data: dict | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    session_id: str | None = None


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UuidStr
    workflow_id: UuidStr
    version_id: OptionalUuidStr = None
    run_type: str
    trigger_type: str
    trigger_data: dict
    triggered_by: UuidStr
    status: str
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    node_runs: list[WorkflowNodeRunResponse] | None = None


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunResponse]
    total: int
