from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings

_engine = None
_async_session = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            connect_args={"timeout": 5},
            pool_pre_ping=True,
        )
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
        pg_add_columns = [
            "ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64) DEFAULT ''",
            "ALTER TABLE personas ADD COLUMN IF NOT EXISTS thinking_framework JSONB DEFAULT '{}'",
            "ALTER TABLE personas ADD COLUMN IF NOT EXISTS voice JSONB DEFAULT '{}'",
            "ALTER TABLE personas ADD COLUMN IF NOT EXISTS core_beliefs JSONB DEFAULT '[]'",
            "ALTER TABLE personas ADD COLUMN IF NOT EXISTS canonical_works JSONB DEFAULT '[]'",
            "ALTER TABLE personas ADD COLUMN IF NOT EXISTS knowledge_domain JSONB DEFAULT '{}'",
            "ALTER TABLE personas ADD COLUMN IF NOT EXISTS skill_config JSONB",
            "ALTER TABLE personas ADD COLUMN IF NOT EXISTS visibility VARCHAR(16) DEFAULT 'public'",
            "ALTER TABLE personas ADD COLUMN IF NOT EXISTS creator_id VARCHAR REFERENCES users(id)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(16) DEFAULT 'user'",
            "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_summarized_seq INTEGER",
        ]
        for stmt in pg_add_columns:
            await conn.execute(text(stmt))