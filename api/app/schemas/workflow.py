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
    current_version: int | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_workflow(cls, workflow, current_version: int | None = None) -> "WorkflowResponse":
        return cls(
            id=str(workflow.id),
            name=workflow.name,
            slug=workflow.slug,
            description=workflow.description,
            owner_id=str(workflow.owner_id),
            definition=workflow.definition,
            model_config=workflow.model_config_json or {},
            status=workflow.status,
            current_version=current_version,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )


class WorkflowListResponse(BaseModel):
    items: list[WorkflowResponse]
    total: int


class WorkflowVersionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    workflow_id: str
    version: int
    deployed_by: str
    deployed_at: datetime

    @classmethod
    def from_orm_version(cls, v) -> "WorkflowVersionResponse":
        return cls(
            id=str(v.id),
            workflow_id=str(v.workflow_id),
            version=v.version,
            deployed_by=str(v.deployed_by),
            deployed_at=v.deployed_at,
        )


class WorkflowRunCreate(BaseModel):
    run_type: str = Field(default="deployed", pattern="^(draft|deployed)$")
    trigger_type: str = Field(default="manual", pattern="^(manual|webhook|cron)$")
    trigger_data: dict = Field(default_factory=dict)


class WorkflowNodeRunResponse(BaseModel):
    id: str
    node_id: str
    node_type: str
    status: str
    input_data: dict | None = None
    output_data: dict | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_orm_node_run(cls, n) -> "WorkflowNodeRunResponse":
        return cls(
            id=str(n.id),
            node_id=n.node_id,
            node_type=n.node_type,
            status=n.status,
            input_data=n.input_data,
            output_data=n.output_data,
            error=n.error,
            started_at=n.started_at,
            completed_at=n.completed_at,
        )


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    version_id: str | None = None
    run_type: str
    trigger_type: str
    trigger_data: dict
    triggered_by: str
    status: str
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    node_runs: list[WorkflowNodeRunResponse] | None = None

    @classmethod
    def from_orm_run(cls, r, include_node_runs: bool = False) -> "WorkflowRunResponse":
        return cls(
            id=str(r.id),
            workflow_id=str(r.workflow_id),
            version_id=str(r.version_id) if r.version_id else None,
            run_type=r.run_type,
            trigger_type=r.trigger_type,
            trigger_data=r.trigger_data or {},
            triggered_by=str(r.triggered_by),
            status=r.status,
            error=r.error,
            started_at=r.started_at,
            completed_at=r.completed_at,
            created_at=r.created_at,
            node_runs=(
                [WorkflowNodeRunResponse.from_orm_node_run(n) for n in r.node_runs]
                if include_node_runs else None
            ),
        )


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunResponse]
    total: int
