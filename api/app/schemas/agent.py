from datetime import datetime

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    # `backend` is opaque to the API server — it's passed through to
    # LiteLLM as the model-name prefix. We don't enforce an allow-list
    # here; LiteLLM will reject unknown backends at request time.
    backend: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_output_tokens: int | None = None


class McpServerConfig(BaseModel):
    name: str
    command: str
    args: list[str] = []


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    description: str | None = None
    instruction: str = Field(..., min_length=1)
    model_config_data: ModelConfig = Field(..., alias="model_config")
    tools: list[str] = []
    mcp_servers: list[McpServerConfig] = []
    visibility: str = Field("private", pattern="^(public|team|private)$")
    category: str | None = None
    icon: str | None = None

    model_config = {"populate_by_name": True}


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    instruction: str | None = Field(None, min_length=1)
    model_config_data: ModelConfig | None = Field(None, alias="model_config")
    tools: list[str] | None = None
    mcp_servers: list[McpServerConfig] | None = None
    visibility: str | None = Field(None, pattern="^(public|team|private)$")
    category: str | None = None
    icon: str | None = None

    model_config = {"populate_by_name": True}


class AgentResponse(BaseModel):
    model_config = {"from_attributes": True, "populate_by_name": True}

    id: str
    name: str
    slug: str
    description: str | None = None
    owner_id: str
    instruction: str
    model_config_data: dict = Field(alias="model_config")
    tools: list
    mcp_servers: list
    visibility: str
    category: str | None = None
    icon: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_agent(cls, agent) -> "AgentResponse":
        return cls(
            id=str(agent.id),
            name=agent.name,
            slug=agent.slug,
            description=agent.description,
            owner_id=str(agent.owner_id),
            instruction=agent.instruction,
            model_config=agent.model_config_json,
            tools=agent.tools,
            mcp_servers=agent.mcp_servers,
            visibility=agent.visibility,
            category=agent.category,
            icon=agent.icon,
            status=agent.status,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int


class AccessibleAgent(BaseModel):
    """Minimal agent info passed to runtime for A2A tool construction."""

    slug: str
    name: str
    description: str | None = None
