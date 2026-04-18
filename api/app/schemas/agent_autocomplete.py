from pydantic import BaseModel, ConfigDict, Field

from app.schemas._common import MODEL_CONFIG_ALIAS
from app.schemas.agent import ModelConfig
from app.schemas.mcp import McpToolResponse


class AgentAutocompleteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    name: str = ""
    description: str = ""
    instruction: str = ""
    model_config_json: ModelConfig = Field(..., **MODEL_CONFIG_ALIAS)
    mcp_tool_ids: list[str] = []
    user_prompt: str | None = None


class AgentAutocompleteResponse(BaseModel):
    name: str
    description: str
    instruction: str
    mcp_tool_ids: list[str]
    tool_info: list[McpToolResponse]
