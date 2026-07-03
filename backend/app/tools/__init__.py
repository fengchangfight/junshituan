"""Tool framework — extensible, lean.

Pattern: each tool is a module exposing a singleton instance of a BaseTool subclass.
Tools register themselves via `tool_registry.register(tool)`.
The agent discovers available tools via `tool_registry.get_schemas()` and invokes
them through `tool_registry.execute(name, args)`.

Add a new tool:
  1. Create `backend/app/tools/my_tool.py`
  2. Subclass `BaseTool`, implement `name`, `description`, `parameters`, `execute()`
  3. Register in `backend/app/tools/__init__.py` → `_register_builtin_tools()`
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Structured result from a tool execution.

    content: plain-text summary for the LLM to read
    data: optional structured data for programmatic use
    """

    content: str
    data: Any = None


class BaseTool(ABC):
    """Minimal tool contract — name, JSON Schema parameters, execute."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name exposed to the LLM (e.g. 'web_search')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description embedded in the system prompt."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema for the tool's input parameters."""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Run the tool. Receives kwargs matching the parameters schema."""
        ...

    @property
    def prompt_snippet(self) -> str:
        """Optional hint injected into the agent's system prompt.
        Override to describe when/how the agent should use this tool.
        """
        return ""

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Simple registry: name → tool instance."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_schemas(self) -> list[dict]:
        """All registered tools as OpenAI function-calling schemas."""
        return [t.to_openai_schema() for t in self._tools.values()]

    def get_prompt_snippets(self) -> str:
        """Aggregated prompt hints for the system prompt."""
        parts = []
        for t in self._tools.values():
            if t.prompt_snippet:
                parts.append(t.prompt_snippet)
        return "\n".join(parts)

    async def execute(self, name: str, args: dict) -> ToolResult:
        """Execute a tool by name with given arguments."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(content=f"Error: unknown tool '{name}'")
        try:
            return await tool.execute(**args)
        except Exception as exc:
            return ToolResult(content=f"Tool '{name}' error: {exc}")

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())


# ── Global singleton ──────────────────────────────────────────────────────────

tool_registry = ToolRegistry()


def _register_builtin_tools():
    """Import and register all built-in tools. Call once at startup."""
    from app.tools.web_search import web_search_tool  # noqa: F401

    for tool in [web_search_tool]:
        tool_registry.register(tool)


_register_builtin_tools()
