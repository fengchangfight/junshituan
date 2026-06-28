"""Context management: compression, pruning, prefix cache.

Inspired by Claude Code's context management strategies:
1. Sliding window with importance-based pruning
2. Conversation summarization for older messages
3. Prefix caching for system prompts (persona definitions)
4. Token counting and budget enforcement
"""

import hashlib
from typing import Optional
from functools import lru_cache

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.core.config import settings
from app.core.llm_client import chat_stream


class ContextManager:
    """Manages conversation context with token budgets."""

    def __init__(self, max_tokens: int = None):
        self.max_tokens = max_tokens or settings.max_context_tokens
        self._prefix_cache: dict[str, tuple[str, str]] = {}  # hash -> (prompt, response)

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation: ~3 chars per token for Chinese, ~4 for English."""
        return len(text) // 3

    def estimate_messages_tokens(self, messages: list[BaseMessage]) -> int:
        total = 0
        for m in messages:
            content = m.content if hasattr(m, "content") else str(m)
            total += self.estimate_tokens(content)
        return total

    def should_compress(self, messages: list[BaseMessage]) -> bool:
        return self.estimate_messages_tokens(messages) > self.max_tokens * 0.75

    async def summarize_history(
        self,
        messages: list[BaseMessage],
        keep_last: int = 4,
    ) -> tuple[str, list[BaseMessage]]:
        """Summarize older messages, keep the most recent ones.

        Returns (summary_text, remaining_messages).
        """
        if len(messages) <= keep_last:
            return "", messages

        to_summarize = messages[:-keep_last]
        recent = messages[-keep_last:]

        conv_text = "\n".join(
            f"[{getattr(m, 'type', '?')}]: {getattr(m, 'content', str(m))[:200]}"
            for m in to_summarize
        )

        prompt = f"""将以下对话历史压缩为一段简洁的摘要。保留：
- 用户的核心问题和困惑
- 各方给出的关键建议和观点
- 任何重要的决策或结论

对话：
{conv_text}

摘要："""

        summary = ""
        async for token in chat_stream(
            system_prompt="你是一个对话摘要助手。简明扼要，保留关键信息。",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        ):
            summary += token

        return summary, recent

    def prune_by_importance(
        self,
        messages: list[BaseMessage],
        budget_tokens: int,
    ) -> list[BaseMessage]:
        """Prune messages to fit within token budget.

        Strategy:
        - Keep system messages
        - Keep most recent messages
        - For older messages, keep only those with high information density
        """
        # Simple approach: keep system + most recent
        system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
        other_msgs = [m for m in messages if not isinstance(m, SystemMessage)]

        result = list(system_msgs)
        token_count = self.estimate_messages_tokens(system_msgs)

        for m in reversed(other_msgs):
            t = self.estimate_tokens(m.content if hasattr(m, "content") else str(m))
            if token_count + t <= budget_tokens:
                result.append(m)
                token_count += t
            else:
                break

        return list(reversed(result))

    def get_prefix_cache_key(self, persona_id: str, system_prompt: str) -> str:
        key = f"{persona_id}:{system_prompt[:200]}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def cache_prefix(self, key: str, prompt: str, response: str):
        self._prefix_cache[key] = (prompt, response)

    def get_cached_prefix(self, key: str) -> Optional[tuple[str, str]]:
        return self._prefix_cache.get(key)

    def build_context_summary(
        self,
        conversation_summary: str,
        user_memories: list[dict],
        advisor_names: list[str],
    ) -> str:
        """Build a concise context summary for injection before new messages."""
        parts = []

        if conversation_summary:
            parts.append(f"[对话摘要]\n{conversation_summary}")

        if user_memories:
            memory_lines = [
                f"- {m['content']}" for m in user_memories[:5]
            ]
            parts.append(f"[用户记忆]\n{chr(10).join(memory_lines)}")

        if parts:
            return "\n\n".join(parts)
        return ""


context_manager = ContextManager()
