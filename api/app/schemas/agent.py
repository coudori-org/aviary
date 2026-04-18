from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._common import MODEL_CONFIG_ALIAS, UuidStr


class ModelConfig(BaseModel):
    # ``backend`` is the LiteLLM model-name prefix; validated at request time
    # by LiteLLM itself.
    backend: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    max_output_tokens: int | None = None


class McpServerConfig(BaseModel):
    name: str
    command: str
    args: list[str] = []


class AgentCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    description: str | None = None
    instruction: str = ""
    model_config_json: ModelConfig = Field(..., **MODEL_CONFIG_ALIAS)
    tools: list[str] = []
    mcp_servers: list[McpServerConfig] = []
    icon: str | None = None


class AgentUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    instruction: str | None = None
    model_config_json: ModelConfig | None = Field(None, **MODEL_CONFIG_ALIAS)
    tools: list[str] | None = None
    mcp_servers: list[McpServerConfig] | None = None
    icon: str | None = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, protected_namespaces=(),
    )

    id: UuidStr
    name: str
    slug: str
    description: str | None = None
    owner_id: UuidStr
    instruction: str
    model_config_json: dict = Field(**MODEL_CONFIG_ALIAS)
    tools: list
    mcp_servers: list
    icon: str | None = None
    runtime_endpoint: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int
