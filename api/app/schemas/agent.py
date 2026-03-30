from datetime import datetime

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    backend: str = Field("claude", pattern="^(claude|ollama|vllm)$")
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.7
    maxTokens: int = 8192


class AgentPolicy(BaseModel):
    maxConcurrentSessions: int = 20
    sessionTimeout: int = 30
    maxTokensPerTurn: int = 100000
    maxMemoryPerSession: str = "512Mi"
    maxCpuPerSession: str = "500m"
    allowedDomains: list[str] = []
    allowShellExec: bool = False
    allowFileWrite: bool = True
    containerImage: str = "aviary-runtime:latest"
    # Pod strategy (agent-per-pod architecture)
    podStrategy: str = "lazy"  # "eager" | "lazy" | "manual"
    minPods: int = 1
    maxPods: int = 3
    maxConcurrentSessionsPerPod: int = 10


class McpServerConfig(BaseModel):
    name: str
    command: str
    args: list[str] = []


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    description: str | None = None
    instruction: str = Field(..., min_length=1)
    model_config_data: ModelConfig = Field(default_factory=ModelConfig, alias="model_config")
    tools: list[str] = []
    mcp_servers: list[McpServerConfig] = []
    policy: AgentPolicy = Field(default_factory=AgentPolicy)
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
    policy: AgentPolicy | None = None
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
    policy: dict
    visibility: str
    category: str | None = None
    icon: str | None = None
    namespace: str | None = None
    pod_strategy: str = "lazy"
    min_pods: int = 1
    max_pods: int = 3
    deployment_active: bool = False
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
            policy=agent.policy,
            visibility=agent.visibility,
            category=agent.category,
            icon=agent.icon,
            namespace=agent.namespace,
            pod_strategy=agent.pod_strategy,
            min_pods=agent.min_pods,
            max_pods=agent.max_pods,
            deployment_active=agent.deployment_active,
            status=agent.status,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int
