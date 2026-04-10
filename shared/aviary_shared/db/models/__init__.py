"""Re-export all models for backward compatibility.

Existing imports like `from aviary_shared.db.models import Agent` continue to work.
"""

from aviary_shared.db.models.base import Base
from aviary_shared.db.models.user import User, Team, TeamMember
from aviary_shared.db.models.agent import Agent, AgentACL, AgentCredential
from aviary_shared.db.models.session import Session, SessionParticipant, Message
from aviary_shared.db.models.mcp import McpServer, McpTool, McpAgentToolBinding, McpToolAcl

__all__ = [
    "Base",
    "User", "Team", "TeamMember",
    "Agent", "AgentACL", "AgentCredential",
    "Session", "SessionParticipant", "Message",
    "McpServer", "McpTool", "McpAgentToolBinding", "McpToolAcl",
]
