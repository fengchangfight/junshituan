"""PostgreSQL-backed LangGraph checkpointer — persists across restarts.

Extends InMemorySaver (native async support) and syncs to agent_checkpoints table.
"""

import json
from typing import Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.base import CheckpointTuple


class PostgresCheckpointer(InMemorySaver):
    """InMemorySaver subclass that persists checkpoints to PostgreSQL.

    On init, loads existing checkpoint from DB. On aput, syncs to DB.
    Falls through to InMemorySaver for all runtime operations.
    """

    async def _get_db(self):
        from app.db.database import _get_sessionmaker
        return _get_sessionmaker()()

    @staticmethod
    def _parse_thread_id(thread_id: str) -> tuple[str, str]:
        parts = thread_id.split("_", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return thread_id, thread_id

    async def aget_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        session_id, advisor_id = self._parse_thread_id(thread_id)

        # Try InMemory first (hot path)
        result = await super().aget_tuple(config)
        if result is not None:
            return result

        # Fall back to DB (after restart)
        try:
            from app.services.memory.session_store import session_store
            db_session = await self._get_db()
            async with db_session as db:
                data = await session_store.get_checkpoint(db, session_id, advisor_id)
                if data is None:
                    return None

                # Deserialize stored state and load into InMemory
                checkpoint = self.serde.loads_typed(data.get("checkpoint", "{}"))
                metadata = data.get("metadata", {})

                config_for_put = {"configurable": config["configurable"]}
                await super().aput(
                    config_for_put,
                    checkpoint,
                    metadata,
                    {},  # new_versions
                )
                # Lockstep: if we're going to put anyway, just return it directly
                return CheckpointTuple(
                    config=config,
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=data.get("parent_config"),
                )
        except Exception as e:
            print(f"[pg_checkpointer] aget_tuple DB fallback error: {e}", flush=True)
            return None

    async def aput(
        self, config, checkpoint, metadata, new_versions
    ):
        thread_id = config["configurable"]["thread_id"]
        session_id, advisor_id = self._parse_thread_id(thread_id)

        # Always save to InMemory (fast path for runtime)
        result = await super().aput(config, checkpoint, metadata, new_versions)

        # Sync to DB (persistent path)
        try:
            data = {
                "checkpoint": self.serde.dumps_typed(checkpoint),
                "metadata": metadata,
                "parent_config": config,
            }
            from app.services.memory.session_store import session_store
            db_session = await self._get_db()
            async with db_session as db:
                await session_store.save_checkpoint(
                    db, session_id, advisor_id, data
                )
        except Exception as e:
            print(f"[pg_checkpointer] aput sync error: {e}", flush=True)

        return result
