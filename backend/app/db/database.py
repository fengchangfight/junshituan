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
        # SQLite compatible ADD COLUMN statements
        sqlite_add_columns = [
            "ALTER TABLE knowledge_documents ADD COLUMN content_hash VARCHAR(64) DEFAULT ''",
            "ALTER TABLE personas ADD COLUMN thinking_framework JSON DEFAULT '{}'",
            "ALTER TABLE personas ADD COLUMN voice JSON DEFAULT '{}'",
            "ALTER TABLE personas ADD COLUMN core_beliefs JSON DEFAULT '[]'",
            "ALTER TABLE personas ADD COLUMN canonical_works JSON DEFAULT '[]'",
            "ALTER TABLE personas ADD COLUMN knowledge_domain JSON DEFAULT '{}'",
            "ALTER TABLE personas ADD COLUMN skill_config JSON",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(16) DEFAULT 'user' NOT NULL",
            "ALTER TABLE users ALTER COLUMN avatar_url TYPE TEXT",
        ]
        for stmt in sqlite_add_columns:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # Column already exists or not SQLite
