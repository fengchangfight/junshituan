"""Hermes-style persistent user memory.

Design principles (inspired by Hermes agent):
1. Extract facts, preferences, and insights from conversations
2. Store with importance scores
3. Retrieve relevant memories for new conversations
4. Periodic consolidation: merge and prune memories
5. Decay: less-accessed memories fade over time
"""

import json
from datetime import datetime, timezone
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import UserMemory
from app.core.llm_client import chat_stream


class UserMemoryService:
    """Manages persistent user memory across sessions."""

    def __init__(self):
        self._consolidation_counter: dict[str, int] = {}

    async def extract_memories(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        conversation: list[dict],
    ) -> list[UserMemory]:
        """Extract memories from a conversation turn.

        Uses LLM to identify facts, preferences, and insights worth remembering.
        """
        if len(conversation) < 2:
            return []

        conv_text = "\n".join(
            f"[{m.get('role', '?')}]: {m.get('content', '')[:300]}"
            for m in conversation[-6:]  # Last 6 messages
        )

        extract_prompt = f"""从以下对话中提取关于用户的重要信息，用于长期记忆。提取类型：
- fact: 用户陈述的事实（如职业、位置、经历）
- preference: 用户的偏好（如喜欢什么、不喜欢什么）
- insight: 用户的洞见或价值观
- event: 用户提到的重要事件

对话：
{conv_text}

返回JSON数组，只提取值得长期记住的信息：
```json
[
  {{"type": "fact", "content": "...", "importance": 0.7}},
  ...
]
```"""

        result = ""
        async for token in chat_stream(
            system_prompt="你是一个记忆提取助手。只输出JSON数组。",
            messages=[{"role": "user", "content": extract_prompt}],
            temperature=0.3,
        ):
            result += token

        memories = []
        try:
            start = result.find("[")
            end = result.rfind("]") + 1
            if start >= 0 and end > start:
                items = json.loads(result[start:end])
                for item in items:
                    memory = UserMemory(
                        user_id=user_id,
                        memory_type=item.get("type", "fact"),
                        content=item.get("content", ""),
                        importance=float(item.get("importance", 0.5)),
                        source_session_id=session_id,
                        last_accessed=datetime.now(timezone.utc),
                    )
                    db.add(memory)
                    memories.append(memory)
                await db.commit()
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        return memories

    async def retrieve_relevant(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        session_id: str = None,
        limit: int = 5,
    ) -> list[dict]:
        """Retrieve memories relevant to the current conversation.

        Session-scoped: memories from the current session always rank first,
        preventing cross-session context leaks. Cross-session memories serve
        only as supplementary user profile.
        """
        stmt = (
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .order_by(UserMemory.importance.desc(), UserMemory.last_accessed.desc().nullslast())
            .limit(limit * 3)
        )
        result = await db.execute(stmt)
        memories = result.scalars().all()

        query_lower = query.lower()
        scored = []
        for m in memories:
            # Base score from importance
            score = m.importance * 0.5

            # Massive boost for current session memories (always top-ranked)
            if session_id and m.source_session_id == session_id:
                score += 100.0

            # Keyword matching boost
            content_lower = m.content.lower()
            for word in query_lower.split():
                if len(word) >= 2 and word in content_lower:
                    score += 0.1

            scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]

        # Update access timestamps
        for _, memory in top:
            memory.access_count += 1
            memory.last_accessed = datetime.now(timezone.utc)

        await db.commit()

        return [
            {
                "id": m.id,
                "type": m.memory_type,
                "content": m.content,
                "importance": m.importance,
            }
            for _, m in top
        ]

    async def consolidate(self, db: AsyncSession, user_id: str):
        """Periodic consolidation: merge similar memories, decay old ones."""
        counter = self._consolidation_counter.get(user_id, 0)
        self._consolidation_counter[user_id] = counter + 1

        if counter % 10 != 0:
            return

        # Decay old memories that haven't been accessed
        threshold = datetime.now(timezone.utc)
        stmt = (
            update(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.last_accessed < threshold,
                UserMemory.importance > 0.1,
            )
            .values(importance=UserMemory.importance * 0.95)
        )
        await db.execute(stmt)

        # Remove very low importance memories if over limit
        count_stmt = select(func.count()).where(UserMemory.user_id == user_id)
        count = (await db.execute(count_stmt)).scalar() or 0

        if count > 100:
            delete_stmt = (
                delete(UserMemory)
                .where(UserMemory.user_id == user_id)
                .order_by(UserMemory.importance.asc())
                .limit(count - 80)
            )
            await db.execute(delete_stmt)

        await db.commit()

    def format_memories_for_prompt(self, memories: list[dict]) -> str:
        """Format memories for injection into system prompt."""
        if not memories:
            return ""

        lines = ["## 关于用户的长久记忆"]
        for m in memories:
            emoji = {"fact": "📋", "preference": "💡", "insight": "🔮", "event": "📅"}.get(
                m["type"], "📌"
            )
            lines.append(f"- {emoji} {m['content']}")
        return "\n".join(lines)


user_memory_service = UserMemoryService()
