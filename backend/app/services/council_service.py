"""Meeting room orchestration service.

Handles:
- Session lifecycle (create, resume, close)
- Parallel advisor agent invocation
- Budget tracking and enforcement
- Memory extraction after each turn
- Context compression when needed
"""

import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Session, ChatMessage
from app.models.schemas import AskEvent
from app.services.agent.agent_registry import agent_registry
from app.services.budget_manager import budget_manager, TokenUsage
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
        session = await session_store.create_session(db, user_id, advisor_ids, title)
        budget = budget_manager.get(session.id)
        await budget_manager.persist(session.id, db)
        return session

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
    ) -> Optional[Session]:
        return await session_store.get_session(db, session_id, user_id)

    async def delete_session(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
    ) -> bool:
        """Delete a session. Returns True if deleted, False if not found or not owner."""
        session = await session_store.get_session(db, session_id, user_id)
        if not session:
            return False
        await session_store.delete_session(db, session_id)
        return True

    async def add_advisors(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
        advisor_ids: list[str],
    ) -> bool:
        """Add advisors to an existing session. Returns False if not owner or not found."""
        session = await session_store.get_session(db, session_id, user_id)
        if not session:
            return False
        return await session_store.add_advisors(db, session_id, advisor_ids)

    async def list_sessions(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> list[dict]:
        sessions = await session_store.list_user_sessions(db, user_id)
        result = []
        for s in sessions:
            budget = budget_manager.get(s.id)
            info = {
                "id": s.id,
                "title": s.title,
                "advisor_ids": s.advisor_ids,
                "message_count": s.message_count,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "updated_at": s.updated_at.isoformat() if s.updated_at else "",
                "budget": budget.to_dict(),
            }
            result.append(info)
        return result

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
        budget = budget_manager.get(session_id)
        return {
            "id": session.id,
            "title": session.title,
            "advisor_ids": session.advisor_ids,
            "message_count": session.message_count,
            "is_active": session.is_active,
            "created_at": session.created_at.isoformat() if session.created_at else "",
            "updated_at": session.updated_at.isoformat() if session.updated_at else "",
            "budget": budget.to_dict(),
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
        target_advisor_id: str = None,
    ):
        """Ask the council a question. Yields SSE events as advisors respond.

        If target_advisor_id is set, only that advisor responds (serial mode).
        Otherwise all advisors respond in parallel.
        """
        print(f"[DEBUG council] ask_council START session={session_id} user={user_id} question={question[:80]}", flush=True)
        session = await self.get_session(db, session_id, user_id)
        if not session:
            print(f"[DEBUG council] session not found", flush=True)
            yield AskEvent(advisor_id="system", content="会话不存在或已过期", done=True)
            return

        advisor_ids = session.advisor_ids or []
        print(f"[DEBUG council] advisor_ids={advisor_ids}", flush=True)
        if target_advisor_id:
            if target_advisor_id not in advisor_ids:
                yield AskEvent(advisor_id="system", content="该军师不在议事厅中", done=True)
                return
            advisor_ids = [target_advisor_id]
        budget = budget_manager.get(session_id)

        if budget.over_budget:
            yield AskEvent(
                advisor_id="system",
                content=f"本会话预算已超支（¥{budget.total_cost_cny:.2f} / ¥{budget.max_budget:.0f}）。请开启新的议事厅。",
                done=True,
            )
            return

        # Estimate cost for this question
        est_input_tokens = len(question) // 2
        est_output_tokens = 800 * len(advisor_ids)  # est 800 tokens per advisor
        est_cost = (
            est_input_tokens / 1_000_000 * budget_manager._input_price()
            + est_output_tokens / 1_000_000 * budget_manager._output_price()
        )

        if not budget.can_spend(est_cost):
            yield AskEvent(
                advisor_id="system",
                content=f"预计本次提问将超出预算（剩余 ¥{budget.remaining_budget:.2f}，预估 ¥{est_cost:.2f}）。请开启新的议事厅。",
                done=True,
            )
            return

        # Emit budget info
        yield AskEvent(
            advisor_id="system",
            content=f"",
            metadata={"type": "budget", "budget": budget.to_dict()},
            done=False,
        )

        # Save user message
        await session_store.add_message(
            db, session_id, role="user", content=question
        )

        # Retrieve user memories for context
        memories = await user_memory_service.retrieve_relevant(db, user_id, question)
        memory_context = user_memory_service.format_memories_for_prompt(memories)

        enhanced_question = question
        if memory_context:
            enhanced_question = f"{memory_context}\n\n[当前问题]\n{question}"

        total_response_chars = 0
        queue: asyncio.Queue[AskEvent] = asyncio.Queue()

        # Collect DB writes to execute after streaming is done
        pending_db_writes: list[dict] = []

        async def ask_one(advisor_id: str):
            nonlocal total_response_chars
            print(f"[DEBUG council] ask_one START advisor={advisor_id}", flush=True)
            try:
                from app.services.persona_engine import get_persona_engine
                engine = get_persona_engine()
                persona = engine.get(advisor_id)
                advisor_name = persona.name if persona else advisor_id

                await queue.put(AskEvent(
                    advisor_id=advisor_id,
                    advisor_name=advisor_name,
                    content="",
                    done=False,
                ))

                response = await agent_registry.ask_advisor(
                    advisor_id, session_id, user_id, enhanced_question, is_resume=is_resume,
                )
                print(f"[DEBUG council] ask_one got response from {advisor_id}: len={len(response)}", flush=True)

                total_response_chars += len(response)

                for chunk in self._chunk_response(response):
                    await queue.put(AskEvent(
                        advisor_id=advisor_id, advisor_name=advisor_name, content=chunk, done=False,
                    ))

                # Defer DB write — don't block the done event
                pending_db_writes.append({
                    "role": "advisor",
                    "content": response,
                    "advisor_id": advisor_id,
                    "advisor_name": advisor_name,
                })
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                safe_tb = tb[:500].encode('ascii', errors='replace').decode('ascii')
                print(f"[DEBUG council] EXCEPTION {advisor_id}: {e}\n{safe_tb}", flush=True)
                await queue.put(AskEvent(
                    advisor_id=advisor_id, advisor_name=advisor_id,
                    content=f"\n[思考受阻：{e}]",
                ))
            finally:
                await queue.put(AskEvent(
                    advisor_id=advisor_id, advisor_name="", content="", done=True,
                ))

        # Process advisors sequentially: start one, drain its events, then next
        for advisor_id in advisor_ids:
            task = asyncio.create_task(ask_one(advisor_id))
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    print(f"[DEBUG council] TIMEOUT waiting for done event from {advisor_id}", flush=True)
                    yield AskEvent(
                        advisor_id=advisor_id, advisor_name="",
                        content="\n[回答超时]", done=True,
                    )
                    break
                yield event
                if event.done:
                    break

        # Record usage
        actual_input = len(enhanced_question) // 2 + len(advisor_ids) * 800
        actual_output = total_response_chars // 2
        usage = TokenUsage(input_tokens=actual_input, output_tokens=actual_output)
        cost = budget.add_usage(usage)

        yield AskEvent(
            advisor_id="system",
            content="",
            metadata={
                "type": "budget_update",
                "cost_this_turn": round(cost, 4),
                "budget": budget.to_dict(),
            },
            done=False,
        )

        # Flush all deferred DB writes + budget persist in background
        # CRITICAL: must NOT block the SSE generator from finishing —
        # otherwise the frontend stays stuck on "thinking" forever.
        asyncio.create_task(self._background_persist(
            session_id, user_id, pending_db_writes, total_response_chars, budget.over_budget,
        ))

    async def _background_persist(
        self, session_id: str, user_id: str,
        pending_writes: list[dict], total_chars: int, over_budget: bool,
    ):
        """Persist advisor messages + budget + memory extraction in background.

        Runs in a separate task so the SSE stream can close immediately after
        the budget_update event, preventing the frontend from hanging.

        Uses its own DB session since the request-scoped session may be closed
        before this task runs.
        """
        from app.db.database import _get_sessionmaker
        try:
            sessionmaker = _get_sessionmaker()
            async with sessionmaker() as bg_db:
                # Save advisor messages
                for w in pending_writes:
                    await session_store.add_message(
                        bg_db, session_id,
                        role=w["role"],
                        content=w["content"],
                        advisor_id=w["advisor_id"],
                        advisor_name=w.get("advisor_name", ""),
                    )

                # Persist budget
                await budget_manager.persist(session_id, bg_db)

            # Memory extraction (uses its own session internally)
            if not over_budget:
                await self._background_extract_memories(
                    session_id, user_id, total_chars
                )
        except Exception as e:
            print(f"[DEBUG council] background persist failed: {e}", flush=True)

    async def _background_extract_memories(self, session_id, user_id, total_chars):
        """Run memory extraction with its own DB session."""
        from app.db.database import _get_sessionmaker
        try:
            sessionmaker = _get_sessionmaker()
            async with sessionmaker() as db:
                group_messages = await session_store.get_messages(db, session_id, limit=20)
                conv = [
                    {"role": m.role, "content": m.content[:500]}
                    for m in group_messages
                ]
                await user_memory_service.extract_memories(db, user_id, session_id, conv)
                if len(group_messages) > 30:
                    summary, _ = await context_manager.summarize_history([], keep_last=10)
                    await session_store.update_summary(db, session_id, summary)
                await user_memory_service.consolidate(db, user_id)
        except Exception as e:
            print(f"[DEBUG council] background memory extraction failed: {e}", flush=True)

    def _chunk_response(self, text: str, chunk_size: int = 50):
        for i in range(0, len(text), chunk_size):
            yield text[i : i + chunk_size]


council_service = CouncilService()

