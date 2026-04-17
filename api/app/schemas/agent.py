from datetime import datetime

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    # `backend` is the LiteLLM model-name prefix; validated at request time by LiteLLM.
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
    instruction: str = ""
    model_config_data: ModelConfig = Field(..., alias="model_config")
    tools: list[str] = []
    mcp_servers: list[McpServerConfig] = []
    icon: str | None = None

    model_config = {"populate_by_name": True}


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    instruction: str | None = None
    model_config_data: ModelConfig | None = Field(None, alias="model_config")
    tools: list[str] | None = None
    mcp_servers: list[McpServerConfig] | None = None
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
            icon=agent.icon,
            status=agent.status,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int
