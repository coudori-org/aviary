"""DB session factory for the controller."""

from aviary_shared.db.session import create_session_factory
from app.config import settings

engine, async_session_factory = create_session_factory(settings.database_url)
