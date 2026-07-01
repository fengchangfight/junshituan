"""Session state persistence — Claude Code resume-session style.

Key features:
1. Full message history stored in PostgreSQL
2. LangGraph checkpoints for agent state
3. Session summary for quick context restoration
4. TTL-based session expiry
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Session, ChatMessage, AgentCheckpoint
from app.core.config import settings


class SessionStore:
    """Manages persistent session state."""

    async def create_session(
        self,
        db: AsyncSession,
        user_id: str,
        advisor_ids: list[str],
        title: str = "",
    ) -> Session:
        session = Session(
            user_id=user_id,
            advisor_ids=advisor_ids,
            title=title,
            is_active=True,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
    ) -> Optional[Session]:
        stmt = select(Session).where(
            Session.id == session_id,
            Session.user_id == user_id,
            Session.is_active == True,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_advisors(
        self,
        db: AsyncSession,
        session_id: str,
        advisor_ids: list[str],
    ) -> bool:
        """Append advisor IDs to an existing session."""
        result = await db.execute(select(Session).where(Session.id == session_id))
        session = result.scalar_one_or_none()
        if not session:
            return False
        current = set(session.advisor_ids or [])
        current.update(advisor_ids)
        session.advisor_ids = list(current)
        await db.commit()
        return True

    async def list_user_sessions(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 20,
    ) -> list[Session]:
        stmt = (
            select(Session)
            .where(Session.user_id == user_id, Session.is_active == True)
            .order_by(desc(Session.updated_at))
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def add_message(
        self,
        db: AsyncSession,
        session_id: str,
        role: str,
        content: str,
        advisor_id: str = None,
        advisor_name: str = "",
        metadata: dict = None,
    ) -> ChatMessage:
        # Get next sequence
        count_stmt = select(ChatMessage).where(
            ChatMessage.session_id == session_id
        )
        result = await db.execute(count_stmt)
        existing = list(result.scalars().all())
        seq = len(existing)

        msg = ChatMessage(
            session_id=session_id,
            sequence=seq,
            role=role,
            advisor_id=advisor_id,
            advisor_name=advisor_name,
            content=content,
            metadata_=metadata or {},
        )
        db.add(msg)

        # Update session stats
        await db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(
                message_count=seq + 1,
                token_count_estimate=Session.token_count_estimate + len(content) // 3,
                updated_at=datetime.now(timezone.utc),
            )
        )

        await db.commit()
        return msg

    async def get_messages(
        self,
        db: AsyncSession,
        session_id: str,
        limit: Optional[int] = None,
    ) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.sequence)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def save_checkpoint(
        self,
        db: AsyncSession,
        session_id: str,
        advisor_id: str,
        checkpoint_data: dict,
    ):
        """Save LangGraph agent checkpoint."""
        # Upsert
        existing_stmt = select(AgentCheckpoint).where(
            AgentCheckpoint.session_id == session_id,
            AgentCheckpoint.advisor_id == advisor_id,
        )
        result = await db.execute(existing_stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.checkpoint_data = checkpoint_data
            existing.created_at = datetime.now(timezone.utc)
        else:
            cp = AgentCheckpoint(
                session_id=session_id,
                advisor_id=advisor_id,
                checkpoint_data=checkpoint_data,
            )
            db.add(cp)

        await db.commit()

    async def get_checkpoint(
        self,
        db: AsyncSession,
        session_id: str,
        advisor_id: str,
    ) -> Optional[dict]:
        stmt = select(AgentCheckpoint).where(
            AgentCheckpoint.session_id == session_id,
            AgentCheckpoint.advisor_id == advisor_id,
        )
        result = await db.execute(stmt)
        cp = result.scalar_one_or_none()
        return cp.checkpoint_data if cp else None

    async def update_summary(
        self,
        db: AsyncSession,
        session_id: str,
        summary: str,
    ):
        await db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(
                conversation_summary=summary,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    async def close_session(self, db: AsyncSession, session_id: str):
        await db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(is_active=False, updated_at=datetime.now(timezone.utc))
        )
        await db.commit()

    async def delete_session(self, db: AsyncSession, session_id: str):
        """Hard delete a session. FK cascades clean up ChatMessage and AgentCheckpoint."""
        result = await db.execute(select(Session).where(Session.id == session_id))
        session = result.scalar_one_or_none()
        if session:
            await db.delete(session)
            await db.commit()

    async def cleanup_expired(self, db: AsyncSession):
        """Remove sessions past TTL."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.session_ttl_hours)
        await db.execute(
            update(Session)
            .where(Session.updated_at < cutoff, Session.is_active == True)
            .values(is_active=False)
        )
        await db.commit()


session_store = SessionStore()
