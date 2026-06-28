"""Sub-agent system inspired by Claude Code sub-agents.

A sub-agent is a lightweight worker that handles a focused sub-task.
It has limited context and returns structured results to the parent agent.
"""

import json
from typing import Optional

from app.core.llm_client import chat_stream


class SubAgent:
    """A focused sub-agent that handles one sub-task at a time."""

    def __init__(
        self,
        name: str = "sub-agent",
        system_instruction: str = "",
        max_tokens: int = 2000,
    ):
        self.name = name
        self.system_instruction = system_instruction
        self.max_tokens = max_tokens

    async def run(
        self,
        task: str,
        parent_context: str = "",
        tools: Optional[list[dict]] = None,
    ) -> str:
        """Execute a sub-task and return results to the parent agent.

        Args:
            task: The specific sub-task description
            parent_context: Context from the parent agent's reasoning
            tools: Optional tool definitions the sub-agent can use

        Returns:
            Structured result string
        """
        prompt = f"""{self.system_instruction}

## 父代理的分析上下文
{parent_context[:1000] if parent_context else '无'}

## 你的子任务
{task}

请完成这个子任务并返回结果。输出JSON格式：
```json
{{
  "result": "你的分析结果",
  "confidence": 0.0-1.0,
  "references": ["引用的来源"]
}}
```"""

        result = ""
        async for token in chat_stream(
            system_prompt=f"你是{self.name}，一个专注于处理子任务的分析助手。只输出JSON。",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        ):
            result += token

        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(result[start:end])
                return json.dumps(parsed, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, ValueError):
            pass

        return result


class SubAgentPool:
    """Pool of pre-configured sub-agent types."""

    TYPES = {
        "analyze": SubAgent(
            name="分析助手",
            system_instruction="你擅长深度分析单个问题，提供有条理的见解。",
        ),
        "verify": SubAgent(
            name="验证助手",
            system_instruction="你负责检验和验证信息，指出不一致之处。",
        ),
        "search_synthesis": SubAgent(
            name="检索综合助手",
            system_instruction="你擅长综合多段检索信息，提取核心观点。",
        ),
        "counterfactual": SubAgent(
            name="反事实分析助手",
            system_instruction="你擅长从对立角度思考问题，挑战假设。",
        ),
    }

    @classmethod
    def get(cls, agent_type: str) -> SubAgent:
        return cls.TYPES.get(agent_type, SubAgent(name=agent_type))


sub_agent_pool = SubAgentPool()
