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

    def __init__(self):
        self._agents: dict[str, AdvisorAgentGraph] = {}

    def get_or_create(self, persona_id: str) -> Optional[AdvisorAgentGraph]:
        """Get or create an agent instance for a persona."""
        if persona_id in self._agents:
            return self._agents[persona_id]

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

        agent = AdvisorAgentGraph(
            persona_id=persona.id,
            persona_name=persona.name,
            system_prompt=persona.build_system_prompt(),
            retrieve_fn=retrieve_knowledge,
            sub_agent_fn=dispatch_sub_agent,
        )

        self._agents[persona_id] = agent
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
        self._agents.pop(persona_id, None)

    def invalidate_all(self):
        """Invalidate all agents (e.g., after global config change)."""
        self._agents.clear()


agent_registry = AgentRegistry()
