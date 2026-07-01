"""Agent registry — manages lifecycle of advisor agent instances.

Each advisor gets one agent instance. The registry ensures:
- One agent per advisor persona (singleton)
- Session-aware execution (each session has its own LangGraph thread)
- Knowledge retrieval is wired to the correct Milvus collection
"""

from typing import Optional

from app.services.agent.base_agent import AdvisorAgentGraph
from app.services.agent.sub_agent import sub_agent_pool
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

        if len(self._agents) >= self._MAX_AGENTS:
            oldest = self._access_order[0]
            self._evict(oldest)

        engine = get_persona_engine()
        persona = engine.get(persona_id)
        if not persona:
            return None

        # Build knowledge retrieval function for this persona
        async def retrieve_knowledge(query: str) -> list[str]:
            docs = await ingest_pipeline.search(persona_id, query, top_k=5)
            return [d["text"] for d in docs]

        # Build sub-agent dispatch
        async def dispatch_sub_agent(task: str, context: str) -> str:
            agent = sub_agent_pool.get("analyze")
            return await agent.run(task, parent_context=context)

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
            sub_agent_fn=dispatch_sub_agent,
        )

        self._agents[persona_id] = agent
        self._access_order.append(persona_id)
        return agent

    async def ask_advisor(
        self,
        persona_id: str,
        session_id: str,
        user_id: str,
        question: str,
        is_resume: bool = False,
    ) -> str:
        """Ask an advisor a question. Handles both new and resumed sessions."""
        agent = self.get_or_create(persona_id)
        if not agent:
            return f"[{persona_id}] 该军师尚未配置。"

        if is_resume:
            return await agent.resume(session_id, user_id, question)
        else:
            return await agent.run(session_id, user_id, question)

    def remove(self, persona_id: str):
        """Remove an agent instance (e.g., when KB is re-ingested)."""
        self._evict(persona_id)

    def invalidate_all(self):
        """Invalidate all agents (e.g., after global config change)."""
        for pid in list(self._agents.keys()):
            self._evict(pid)

    def _bump_access(self, persona_id: str):
        if persona_id in self._access_order:
            self._access_order.remove(persona_id)
        self._access_order.append(persona_id)

    def _evict(self, persona_id: str):
        """Evict an agent and its in-memory checkpoints."""
        self._agents.pop(persona_id, None)
        if persona_id in self._access_order:
            self._access_order.remove(persona_id)


agent_registry = AgentRegistry()
