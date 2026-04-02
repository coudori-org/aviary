"""DB session factory using shared package."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.session import create_session_factory
from app.config import settings

engine, async_session_factory = create_session_factory(settings.database_url)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
