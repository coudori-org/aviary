"""DB session factory for the agent supervisor."""

from aviary_shared.db.session import create_session_factory
from app.config import settings

engine, async_session_factory = create_session_factory(settings.database_url)
