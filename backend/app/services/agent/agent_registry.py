"""Agent registry — manages lifecycle of advisor agent instances.

Each advisor gets one agent instance. The registry ensures:
- One agent per advisor persona (singleton)
- Session-aware execution (each session has its own LangGraph thread)
- Knowledge retrieval is wired to the correct Milvus collection
- Streaming: on_token callback fires per LLM token for real-time frontend updates
"""

import time
from typing import Optional, Callable, Awaitable

from app.services.agent.base_agent import AdvisorAgentGraph
from app.services.ingestion.pipeline import pipeline as ingest_pipeline
from app.services.persona_engine import get_persona_engine


class AgentRegistry:
    """Manages active advisor agent instances."""

    _MAX_AGENTS = 20

    def __init__(self):
        self._agents: dict[str, AdvisorAgentGraph] = {}
        self._access_order: list[str] = []

    def get_or_create(self, persona_id: str) -> Optional[AdvisorAgentGraph]:
        """Get or create an agent instance for a persona."""
        if persona_id in self._agents:
            self._bump_access(persona_id)
            return self._agents[persona_id]

        print(f"[DEBUG registry] get_or_create cache MISS for {persona_id}, creating...", flush=True)

        if len(self._agents) >= self._MAX_AGENTS:
            oldest = self._access_order[0]
            self._evict(oldest)

        engine = get_persona_engine()
        persona = engine.get(persona_id)
        if not persona:
            print(f"[DEBUG registry] persona {persona_id} not found", flush=True)
            return None
        print(f"[DEBUG registry] creating agent for {persona.name} kb_doc_count={persona.kb_doc_count}", flush=True)

        # Skip Milvus entirely when persona has zero documents (saves ~1.4s)
        if persona.kb_doc_count > 0:
            async def retrieve_knowledge(query: str) -> list[str]:
                print(f"[DEBUG registry] retrieve_knowledge START persona={persona_id} query={query[:60]}", flush=True)
                docs = await ingest_pipeline.search(persona_id, query, top_k=5)
                print(f"[DEBUG registry] retrieve_knowledge DONE persona={persona_id} got {len(docs)} docs", flush=True)
                return [d["text"] for d in docs]
        else:
            async def retrieve_knowledge(query: str) -> list[str]:
                print(f"[TIMING registry] retrieve_knowledge SKIPPED (no docs) persona={persona_id}", flush=True)
                return []

        # Build skill-enhanced system prompt
        from app.services.skill_engine import get_skill_engine
        skill_engine = get_skill_engine()
        skill_prompt = skill_engine.build_skill_prompt(persona_id)
        system_prompt = persona.build_system_prompt(skill_prompt=skill_prompt)

        agent = AdvisorAgentGraph(
            persona_id=persona.id,
            persona_name=persona.name,
            system_prompt=system_prompt,
            retrieve_fn=retrieve_knowledge,
        )

        self._agents[persona_id] = agent
        self._access_order.append(persona_id)
        return agent

    async def ask_advisor(
        self, persona_id: str, session_id: str, user_id: str,
        question: str, is_resume: bool = False,
        history: Optional[list[dict]] = None,
    ) -> str:
        """Ask advisor (non-streaming). Returns full response string."""
        return await self._ask_impl(persona_id, session_id, user_id, question, is_resume, history=history)

    async def ask_advisor_streaming(
        self, persona_id: str, session_id: str, user_id: str,
        question: str, is_resume: bool,
        on_token: Callable[[str], Awaitable[None]],
        on_tool_progress: Optional[Callable[[dict], Awaitable[None]]] = None,
        history: Optional[list[dict]] = None,
    ) -> str:
        """Ask advisor with per-token streaming callback.

        on_token is called for every LLM output token as it arrives.
        on_tool_progress: called when tools are being executed.
        history: conversation history for context when no checkpoint exists.
        """
        return await self._ask_impl(persona_id, session_id, user_id, question, is_resume, on_token, on_tool_progress, history)

    async def _ask_impl(
        self, persona_id: str, session_id: str, user_id: str,
        question: str, is_resume: bool,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_tool_progress: Optional[Callable[[dict], Awaitable[None]]] = None,
        history: Optional[list[dict]] = None,
    ) -> str:
        print(f"[DEBUG registry] ask_advisor START persona={persona_id} session={session_id} is_resume={is_resume} streaming={on_token is not None} history_len={len(history) if history else 0}", flush=True)
        agent = self.get_or_create(persona_id)
        if not agent:
            return f"[{persona_id}] 该军师尚未配置。"

        print(f"[DEBUG registry] calling agent.{'resume' if is_resume else 'run'}...", flush=True)
        t0 = time.perf_counter()
        if is_resume:
            result = await agent.resume(session_id, user_id, question, on_token=on_token, on_tool_progress=on_tool_progress, history=history)
        else:
            result = await agent.run(session_id, user_id, question, on_token=on_token, on_tool_progress=on_tool_progress, history=history)
        print(f"[TIMING registry] ask_advisor took {(time.perf_counter() - t0)*1000:.0f}ms", flush=True)
        return result

    def remove(self, persona_id: str):
        self._evict(persona_id)

    def invalidate_all(self):
        for pid in list(self._agents.keys()):
            self._evict(pid)

    def _bump_access(self, persona_id: str):
        if persona_id in self._access_order:
            self._access_order.remove(persona_id)
        self._access_order.append(persona_id)

    def _evict(self, persona_id: str):
        self._agents.pop(persona_id, None)
        if persona_id in self._access_order:
            self._access_order.remove(persona_id)


agent_registry = AgentRegistry()
