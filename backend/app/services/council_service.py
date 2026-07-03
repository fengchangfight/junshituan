from app.core.logging import get_logger

log = get_logger("council")

"""Meeting room orchestration service.

Handles:
- Session lifecycle (create, resume, close)
- Parallel advisor agent invocation
- Budget tracking and enforcement
- Memory extraction after each turn
- Context compression when needed
"""

import asyncio
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Session
from app.models.schemas import AskEvent
from app.services.agent.agent_registry import agent_registry
from app.services.budget_manager import budget_manager, TokenUsage
from app.services.memory.session_store import session_store
from app.services.memory.user_memory import user_memory_service
from app.services.memory.context_manager import context_manager


class CouncilService:
    """Orchestrates multi-advisor chat sessions."""

    def __init__(self):
        # Track pending background persist tasks per session.
        # Awaited before loading history to ensure DB consistency.
        self._pending_persists: dict[str, asyncio.Task] = {}

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
        target_advisor_ids: list[str] = None,
    ):
        """Ask the council a question. Yields SSE events as advisors respond.

        If target_advisor_ids is set, only those advisors respond sequentially.
        Each subsequent advisor sees accumulated context from prior responses.
        """
        t0 = time.perf_counter()
        log.timing(f"ask_council START session={session_id} user={user_id} question={question[:80]}")
        session = await self.get_session(db, session_id, user_id)
        log.timing(f"get_session took {(time.perf_counter() - t0)*1000:.0f}ms")
        if not session:
            log.debug(f"session not found")
            yield AskEvent(advisor_id="system", content="会话不存在或已过期", done=True)
            return

        advisor_ids = session.advisor_ids or []
        log.debug(f"advisor_ids={advisor_ids}")
        if target_advisor_ids:
            valid = [a for a in target_advisor_ids if a in advisor_ids]
            if not valid:
                yield AskEvent(advisor_id="system", content="指定的军师不在议事厅中", done=True)
                return
            advisor_ids = valid
            log.debug(f"multi-target mode: {len(advisor_ids)} advisors")
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
            est_input_tokens / 1_000_000 * budget_manager.input_price()
            + est_output_tokens / 1_000_000 * budget_manager.output_price()
        )

        if not budget.can_spend(est_cost):
            yield AskEvent(
                advisor_id="system",
                content=f"预计本次提问将超出预算（剩余 ¥{budget.remaining_budget:.2f}，预估 ¥{est_cost:.2f}）。请开启新的议事厅。",
                done=True,
            )
            return

        # Emit budget info
        t_adv_start = time.perf_counter()
        yield AskEvent(
            advisor_id="system",
            content=f"",
            metadata={"type": "budget", "budget": budget.to_dict()},
            done=False,
        )
        log.timing(f"pre-advisor setup took {(time.perf_counter() - t0)*1000:.0f}ms total")

        # Load conversation history BEFORE saving the current user message.
        # This ensures history contains only prior messages, not the current
        # question (which is passed separately as enhanced_question).
        conversation_history: list[dict] = []
        if is_resume:
            pending = self._pending_persists.pop(session_id, None)
            if pending and not pending.done():
                await pending
            history_msgs = await session_store.get_messages(db, session_id)
            conversation_history = [
                {"role": m.role, "content": m.content, "advisor_name": m.advisor_name or ""}
                for m in history_msgs
            ]
            log.timing(f"loaded {len(conversation_history)} history messages")

        # Save user message
        t1 = time.perf_counter()
        await session_store.add_message(
            db, session_id, role="user", content=question
        )
        log.timing(f"save_user_msg took {(time.perf_counter() - t1)*1000:.0f}ms")

        # Retrieve user memories for context (session-scoped)
        t2 = time.perf_counter()
        memories = await user_memory_service.retrieve_relevant(db, user_id, question, session_id=session_id)
        # Only inject memories when the question has semantic content.
        if len(question) >= 10 and "继续发言" not in question:
            memory_context = user_memory_service.format_memories_for_prompt(memories)
        else:
            memory_context = ""
            memories = []
        log.timing(f"retrieve_memories took {(time.perf_counter() - t2)*1000:.0f}ms, got {len(memories)} memories, injected={bool(memory_context)}")

        enhanced_question = question
        if memory_context:
            enhanced_question = f"{memory_context}\n\n[当前问题]\n{question}"

        total_response_chars = 0
        queue: asyncio.Queue[AskEvent] = asyncio.Queue()

        # Collect DB writes to execute after streaming is done
        pending_db_writes: list[dict] = []

        async def ask_one(advisor_id: str):
            nonlocal total_response_chars
            log.debug(f"ask_one START advisor={advisor_id}")
            try:
                from app.services.persona_engine import get_persona_engine
                engine = get_persona_engine()
                persona = engine.get(advisor_id)
                advisor_name = persona.name if persona else advisor_id

                # Initial ping — frontend creates pending message
                await queue.put(AskEvent(
                    advisor_id=advisor_id,
                    advisor_name=advisor_name,
                    content="",
                    done=False,
                ))

                # Streaming agent: each LLM token → queue → SSE → frontend in real time
                t_stream = time.perf_counter()

                async def _on_tool_progress(progress):
                    await queue.put(AskEvent(
                        advisor_id=advisor_id, advisor_name=advisor_name, content="", done=False,
                        metadata={"type": "tool_progress", "action": progress.get("action"), "tool_name": progress.get("tool_name"),
                                  "query": progress.get("query", ""), "result_count": progress.get("result_count", 0),
                                  "results": progress.get("results", [])},
                    ))

                response = await agent_registry.ask_advisor_streaming(
                    advisor_id, session_id, user_id, enhanced_question,
                    is_resume=is_resume,
                    history=conversation_history if is_resume else None,
                    on_token=lambda token, _name=advisor_name, _aid=advisor_id: queue.put(
                        AskEvent(advisor_id=_aid, advisor_name=_name, content=token, done=False)
                    ),
                    on_tool_progress=_on_tool_progress,
                )
                log.debug(f"ask_one got response from {advisor_id}: len={len(response)} streamed in {(time.perf_counter() - t_stream)*1000:.0f}ms")

                total_response_chars += len(response)

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
                log.debug(f"EXCEPTION {advisor_id}: {e}\n{safe_tb}")
                await queue.put(AskEvent(
                    advisor_id=advisor_id, advisor_name=advisor_id,
                    content=f"\n[思考受阻：{e}]",
                ))
            finally:
                await queue.put(AskEvent(
                    advisor_id=advisor_id, advisor_name="", content="", done=True,
                ))

        # Process advisors sequentially: start one, drain its events, then next.
        # Accumulate responses so each subsequent advisor sees prior context.
        base_question = enhanced_question
        accumulated_context = ""

        for advisor_id in advisor_ids:
            t_adv = time.perf_counter()

            # Build question with accumulated prior responses
            if accumulated_context:
                enhanced_question = f"{base_question}\n\n## 前面军师的发言（请在此基础上回应）\n{accumulated_context}"

            task = asyncio.create_task(ask_one(advisor_id))
            advisor_response_text = ""

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    log.debug(f"TIMEOUT waiting for done event from {advisor_id}")
                    yield AskEvent(
                        advisor_id=advisor_id, advisor_name="",
                        content="\n[回答超时]", done=True,
                    )
                    break
                if event.content and not event.done:
                    advisor_response_text += event.content
                yield event
                if event.done:
                    from app.services.persona_engine import get_persona_engine
                    engine = get_persona_engine()
                    persona = engine.get(advisor_id)
                    advisor_name = persona.name if persona else advisor_id
                    accumulated_context += f"[{advisor_name}]: {advisor_response_text}\n"
                    log.timing(f"advisor {advisor_id} total took {(time.perf_counter() - t_adv)*1000:.0f}ms")
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
        task = asyncio.create_task(self._background_persist(
            session_id, user_id, pending_db_writes, total_response_chars, budget.over_budget,
        ))
        self._pending_persists[session_id] = task
        log.timing(f"ask_council DONE total={(time.perf_counter() - t0)*1000:.0f}ms")

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
            log.debug(f"background persist failed: {e}")

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
                    from langchain_core.messages import HumanMessage, AIMessage
                    lc_messages = []
                    for gm in group_messages:
                        if gm.role == "user":
                            lc_messages.append(HumanMessage(content=gm.content[:500]))
                        else:
                            lc_messages.append(AIMessage(content=gm.content[:500]))
                    summary, _ = await context_manager.summarize_history(lc_messages, keep_last=10)
                    if summary:
                        await session_store.update_summary(db, session_id, summary)
                await user_memory_service.consolidate(db, user_id)
        except Exception as e:
            log.debug(f"background memory extraction failed: {e}")

council_service = CouncilService()

