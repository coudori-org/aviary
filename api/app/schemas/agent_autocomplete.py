from pydantic import BaseModel, Field

from app.schemas.agent import ModelConfig
from app.schemas.mcp import McpToolResponse


class AgentAutocompleteRequest(BaseModel):
    name: str = ""
    description: str = ""
    instruction: str = ""
    model_config_data: ModelConfig = Field(..., alias="model_config")
    mcp_tool_ids: list[str] = []
    user_prompt: str | None = None

    model_config = {"populate_by_name": True}


class AgentAutocompleteResponse(BaseModel):
    name: str
    description: str
    instruction: str
    mcp_tool_ids: list[str]
    tool_info: list[McpToolResponse]
