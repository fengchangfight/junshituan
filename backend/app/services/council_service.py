"""Meeting room orchestration service.

Handles:
- Session lifecycle (create, resume, close)
- Parallel advisor agent invocation
- Memory extraction after each turn
- Context compression when needed
"""

import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Session, ChatMessage
from app.models.schemas import AskEvent
from app.services.agent.agent_registry import agent_registry
from app.services.memory.session_store import session_store
from app.services.memory.user_memory import user_memory_service
from app.services.memory.context_manager import context_manager


class CouncilService:
    """Orchestrates multi-advisor chat sessions."""

    async def create_session(
        self,
        db: AsyncSession,
        user_id: str,
        advisor_ids: list[str],
        title: str = "",
    ) -> Session:
        return await session_store.create_session(db, user_id, advisor_ids, title)

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
    ) -> Optional[Session]:
        return await session_store.get_session(db, session_id, user_id)

    async def list_sessions(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> list[dict]:
        sessions = await session_store.list_user_sessions(db, user_id)
        return [
            {
                "id": s.id,
                "title": s.title,
                "advisor_ids": s.advisor_ids,
                "message_count": s.message_count,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "updated_at": s.updated_at.isoformat() if s.updated_at else "",
            }
            for s in sessions
        ]

    async def get_session_detail(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
    ) -> Optional[dict]:
        session = await self.get_session(db, session_id, user_id)
        if not session:
            return None

        messages = await session_store.get_messages(db, session_id)
        return {
            "id": session.id,
            "title": session.title,
            "advisor_ids": session.advisor_ids,
            "message_count": session.message_count,
            "is_active": session.is_active,
            "created_at": session.created_at.isoformat() if session.created_at else "",
            "updated_at": session.updated_at.isoformat() if session.updated_at else "",
            "messages": [
                {
                    "id": m.id,
                    "sequence": m.sequence,
                    "role": m.role,
                    "advisor_id": m.advisor_id,
                    "advisor_name": m.advisor_name,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else "",
                    "metadata": m.metadata_ or {},
                }
                for m in messages
            ],
        }

    async def ask_council(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
        user_name: str,
        question: str,
        is_resume: bool = False,
    ):
        """Ask the council a question. Yields SSE events as advisors respond.

        Each advisor responds in parallel via their agent instance.
        """
        session = await self.get_session(db, session_id, user_id)
        if not session:
            yield AskEvent(advisor_id="system", content="会话不存在或已过期", done=True)
            return

        # Save user message
        await session_store.add_message(
            db, session_id, role="user", content=question
        )

        # Retrieve user memories for context
        memories = await user_memory_service.retrieve_relevant(db, user_id, question)
        memory_context = user_memory_service.format_memories_for_prompt(memories)

        # Enhance question with memory context if available
        enhanced_question = question
        if memory_context:
            enhanced_question = f"{memory_context}\n\n[当前问题]\n{question}"

        advisor_ids = session.advisor_ids or []
        queue: asyncio.Queue[AskEvent | None] = asyncio.Queue()

        async def ask_one(advisor_id: str):
            try:
                from app.services.persona_engine import get_persona_engine
                engine = get_persona_engine()
                persona = engine.get(advisor_id)
                advisor_name = persona.name if persona else advisor_id

                # Emit "thinking" event
                await queue.put(AskEvent(
                    advisor_id=advisor_id,
                    advisor_name=advisor_name,
                    content="",
                    done=False,
                ))

                response = await agent_registry.ask_advisor(
                    advisor_id,
                    session_id,
                    user_id,
                    enhanced_question,
                    is_resume=is_resume,
                )

                # Save advisor response via queue for streaming
                for chunk in self._chunk_response(response, chunk_size=50):
                    await queue.put(AskEvent(
                        advisor_id=advisor_id,
                        advisor_name=advisor_name,
                        content=chunk,
                        done=False,
                    ))

                # Save full response to DB
                await session_store.add_message(
                    db,
                    session_id,
                    role="advisor",
                    advisor_id=advisor_id,
                    advisor_name=advisor_name,
                    content=response,
                )

            except Exception as e:
                await queue.put(AskEvent(
                    advisor_id=advisor_id,
                    advisor_name=advisor_id,
                    content=f"\n[思考受阻：{e}]",
                ))
            finally:
                await queue.put(AskEvent(
                    advisor_id=advisor_id,
                    advisor_name="",
                    content="",
                    done=True,
                ))

        tasks = [asyncio.create_task(ask_one(aid)) for aid in advisor_ids]
        done_count = 0
        total = len(tasks)

        while done_count < total:
            event = await queue.get()
            if event.done:
                done_count += 1
            yield event

        await asyncio.gather(*tasks)

        # Extract memories from this conversation turn
        group_messages = await session_store.get_messages(db, session_id, limit=20)
        conv = [
            {"role": m.role, "content": m.content[:500]}
            for m in group_messages
        ]
        await user_memory_service.extract_memories(db, user_id, session_id, conv)

        # Check if compression needed
        if len(group_messages) > 30:
            summary, _ = await context_manager.summarize_history(
                [],  # We use DB messages, not LangChain messages here
                keep_last=10,
            )
            await session_store.update_summary(db, session_id, summary)

        # Periodic memory consolidation
        await user_memory_service.consolidate(db, user_id)

    def _chunk_response(self, text: str, chunk_size: int = 50):
        """Yield text in chunks for streaming."""
        for i in range(0, len(text), chunk_size):
            yield text[i : i + chunk_size]


council_service = CouncilService()
