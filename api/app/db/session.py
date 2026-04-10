"""DB session factory using shared package."""

from aviary_shared.db.session import create_session_factory, get_db_dependency
from app.config import settings

engine, async_session_factory = create_session_factory(settings.database_url)


async def get_db():
    async for session in get_db_dependency(async_session_factory):
        yield session
