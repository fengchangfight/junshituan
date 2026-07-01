from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings

_engine = None
_async_session = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, echo=False)
    return _engine


def _get_sessionmaker():
    global _async_session
    if _async_session is None:
        _async_session = async_sessionmaker(_get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _async_session


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with _get_sessionmaker()() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Auto-migration: add columns that may be missing on existing tables
        try:
            await conn.execute(text(
                "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64) DEFAULT ''"
            ))
        except Exception:
            pass  # SQLite doesn't support ADD COLUMN IF NOT EXISTS
