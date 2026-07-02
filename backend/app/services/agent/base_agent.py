"""LangGraph-based agent template for advisor reasoning.

Streaming architecture (key design decision):
- _reason outputs tagged format: <complexity> <reasoning> <response>
- StreamTagParser extracts <response> tokens on-the-fly
- token_callback fires per-token → council drains → SSE → frontend
- Result: user sees words stream in after TTFT, not after full generation

Graph:
  understand → retrieve → reason ──[simple]──→ END
                                    └──[complex]──→ respond → END
"""

import asyncio
import json
import time
from typing import TypedDict, Annotated, Literal, Optional, Callable, Awaitable

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage

from app.core.config import settings
from app.core.llm_client import chat_stream


# ── Streaming Tag Parser ──────────────────────────────────────────────────

class StreamTagParser:
    """Parse XML-like tags from a streaming text source.

    Usage:
        parser = StreamTagParser(["complexity", "reasoning", "response"])
        for token in stream:
            forward = parser.feed(token)
            if forward:
                send_to_frontend(forward)
        result = parser.results  # {"complexity": "...", "reasoning": "...", "response": "..."}
    """

    def __init__(self, tags: list[str]):
        self.tags = tags
        self.results: dict[str, str] = {t: "" for t in tags}
        self._buffer = ""
        self._current_tag: Optional[str] = None  # currently inside this tag
        self._done_tags: set[str] = set()

    def feed(self, token: str) -> Optional[str]:
        """Feed a token. Returns text to forward (inside <response>), or None."""
        self._buffer += token

        if self._current_tag is None:
            # Looking for an opening tag
            return self._scan_for_open()
        else:
            # Inside a tag, looking for closing tag
            return self._scan_for_close()

    def _scan_for_open(self) -> Optional[str]:
        forward = None
        for tag in self.tags:
            if tag in self._done_tags:
                continue
            open_tag = f"<{tag}>"
            idx = self._buffer.find(open_tag)
            if idx >= 0:
                self._current_tag = tag
                after = self._buffer[idx + len(open_tag):]
                self._buffer = after
                if tag == "response":
                    # Check if close tag is already in buffer
                    close_tag = f"</{tag}>"
                    end_idx = self._buffer.find(close_tag)
                    if end_idx >= 0:
                        content = self._buffer[:end_idx]
                        self.results[tag] = content
                        self._current_tag = None
                        self._done_tags.add(tag)
                        self._buffer = self._buffer[end_idx + len(close_tag):]
                        return content
                    return ""  # Start streaming, nothing to forward yet
                break

        # Prevent unbounded buffer growth (keep tail for partial tag match)
        max_tag_len = max(len(f"<{t}>") for t in self.tags)
        if len(self._buffer) > max_tag_len * 2:
            self._buffer = self._buffer[-max_tag_len:]
        return forward

    def _scan_for_close(self) -> Optional[str]:
        tag = self._current_tag
        close_tag = f"</{tag}>"
        idx = self._buffer.find(close_tag)

        if idx >= 0:
            content = self._buffer[:idx]
            self.results[tag] = (self.results.get(tag, "") + content).strip()
            self._current_tag = None
            self._done_tags.add(tag)
            self._buffer = self._buffer[idx + len(close_tag):]
            if tag == "response":
                return content
            return None

        # No close tag yet — forward safe portion, keep tail for partial tag
        safe_len = max(0, len(self._buffer) - len(close_tag))
        if safe_len > 0 and tag == "response":
            result = self._buffer[:safe_len]
            self._buffer = self._buffer[safe_len:]
            return result

        return None

    @property
    def is_done(self) -> bool:
        return len(self._done_tags) == len(self.tags)


# ── State ──────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    persona_id: str
    persona_name: str
    system_prompt: str
    session_id: str
    user_id: str

    # Retrieval
    retrieved_docs: list[str]
    retrieval_query: str

    # Reasoning
    reasoning: str
    complexity: str

    # Context management
    context_summary: str
    tokens_used: int

    # Final output
    final_response: str


# ── Agent Graph Builder ────────────────────────────────────────────────────

class AdvisorAgentGraph:
    """Base agent graph for an advisor."""

    def __init__(
        self,
        persona_id: str,
        persona_name: str,
        system_prompt: str,
        retrieve_fn,
        sub_agent_fn=None,
        checkpointer: Optional[BaseCheckpointSaver] = None,
    ):
        self.persona_id = persona_id
        self.persona_name = persona_name
        self.system_prompt = system_prompt
        self.retrieve_fn = retrieve_fn
        self.sub_agent_fn = sub_agent_fn
        self.checkpointer = checkpointer or MemorySaver()
        self._token_callback: Optional[Callable[[str], Awaitable[None]]] = None
        self.graph = self._build()

    def set_token_callback(self, cb: Optional[Callable[[str], Awaitable[None]]]):
        self._token_callback = cb

    def _build(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        workflow.add_node("understand", self._understand)
        workflow.add_node("retrieve", self._retrieve)
        workflow.add_node("reason", self._reason)
        workflow.add_node("respond", self._respond)
        workflow.add_node("compress", self._compress)

        workflow.add_edge(START, "understand")
        workflow.add_edge("understand", "retrieve")
        workflow.add_edge("retrieve", "reason")

        workflow.add_conditional_edges(
            "reason",
            self._decide_complexity,
            {"simple": END, "complex": "respond"},
        )

        workflow.add_conditional_edges(
            "respond",
            self._check_context,
            {"compress": "compress", "end": END},
        )

        workflow.add_edge("compress", END)

        return workflow.compile(checkpointer=self.checkpointer)

    # ── Nodes ──────────────────────────────────────────────────────────────

    async def _understand(self, state: AgentState) -> dict:
        t0 = time.perf_counter()
        msgs = state.get("messages", [])
        last_msg = msgs[-1].content if msgs else ""
        print(f"[TIMING agent:{self.persona_id}] _understand took {(time.perf_counter() - t0)*1000:.0f}ms", flush=True)
        return {"retrieval_query": last_msg}

    async def _retrieve(self, state: AgentState) -> dict:
        t0 = time.perf_counter()
        query = state.get("retrieval_query", "")
        if self.retrieve_fn and query:
            print(f"[DEBUG agent:{self.persona_id}] _retrieve calling retrieve_fn...", flush=True)
            docs = await self.retrieve_fn(query)
            print(f"[TIMING agent:{self.persona_id}] _retrieve took {(time.perf_counter() - t0)*1000:.0f}ms, got {len(docs)} docs", flush=True)
            return {"retrieved_docs": docs}
        print(f"[TIMING agent:{self.persona_id}] _retrieve skipped {(time.perf_counter() - t0)*1000:.0f}ms", flush=True)
        return {"retrieved_docs": []}

    async def _reason(self, state: AgentState) -> dict:
        """Analyze + respond in one LLM call using tag-delimited output.

        Output format (streaming-parsed):
          <complexity>simple</complexity>
          <reasoning>brief analysis...</reasoning>
          <response>the final answer streamed to user</response>

        Token callback receives <response> content tokens in real time.
        """
        t0 = time.perf_counter()
        print(f"[DEBUG agent:{self.persona_id}] _reason START", flush=True)

        docs = state.get("retrieved_docs", [])
        docs_text = "\n---\n".join(docs[:5]) if docs else ""
        msgs = state.get("messages", [])
        question = msgs[-1].content if msgs else '无'

        prompt = f"""{self.system_prompt}

## 参考资料
{docs_text if docs_text else '无相关参考资料'}

## 用户问题
{question}

## 输出格式

必须使用以下标签格式输出，标签单独占一行：

<complexity>simple</complexity>
<reasoning>
简短分析（2-3句）
</reasoning>
<response>
你的最终回答（以{self.persona_name}的第一人称）
</response>

### 判断标准

complexity=simple（多数情况）：日常问答、观点表达、知识介绍，可直接回答。
complexity=complex：需要多步推理、对比分析、数学计算、用户明确要求"深入分析"。

### 要求
1. 你是{self.persona_name}本人，response用第一人称直接说话
2. response 150-400字，简洁有力
3. 可引用著作或名言，但点到为止"""

        print(f"[DEBUG agent:{self.persona_id}] _reason calling chat_stream...", flush=True)
        parser = StreamTagParser(["complexity", "reasoning", "response"])
        raw = ""
        async for token in chat_stream(
            system_prompt="",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
        ):
            raw += token
            forward = parser.feed(token)
            if forward and self._token_callback:
                await self._token_callback(forward)

        complexity = parser.results.get("complexity", "simple").strip()
        reasoning = parser.results.get("reasoning", "").strip()
        response = parser.results.get("response", "").strip()

        # Fallback: if response is empty, try raw text
        if not response:
            response = raw
            complexity = "simple"

        print(f"[TIMING agent:{self.persona_id}] _reason took {(time.perf_counter() - t0)*1000:.0f}ms complexity={complexity} reasoning={len(reasoning)}chars response={len(response)}chars", flush=True)

        return {
            "reasoning": reasoning,
            "complexity": complexity,
            "final_response": response if complexity == "simple" else "",
        }

    async def _respond(self, state: AgentState) -> dict:
        """Polish final response for complex questions. Streams tokens directly."""
        t0 = time.perf_counter()
        print(f"[DEBUG agent:{self.persona_id}] _respond START (complex)", flush=True)

        reasoning = state.get("reasoning", "")
        docs = state.get("retrieved_docs", [])
        docs_text = "\n---\n".join(docs[:3]) if docs else ""
        msgs = state.get("messages", [])
        question = msgs[-1].content if msgs else ''

        prompt = f"""{self.system_prompt}

## 前序分析
{reasoning}

## 参考资料
{docs_text if docs_text else '无'}

## 用户问题
{question}

请基于前序分析，以{self.persona_name}的身份直接给出最终回答。
1. 第一人称，直接说话
2. 200-500字，有深度但不冗长"""

        print(f"[DEBUG agent:{self.persona_id}] _respond calling chat_stream...", flush=True)
        full = ""
        async for token in chat_stream(
            system_prompt="",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
        ):
            full += token
            if self._token_callback:
                await self._token_callback(token)

        print(f"[TIMING agent:{self.persona_id}] _respond took {(time.perf_counter() - t0)*1000:.0f}ms response={len(full)}chars", flush=True)
        return {"final_response": full}

    async def _compress(self, state: AgentState) -> dict:
        t0 = time.perf_counter()
        print(f"[TIMING agent:{self.persona_id}] _compress START", flush=True)
        msgs = state.get("messages", [])
        if len(msgs) <= 4:
            return {}

        summary_prompt = f"""请将以下对话历史压缩为一段简洁的摘要：

{self._format_history(msgs[:-2])}

摘要："""

        summary = ""
        async for token in chat_stream(
            system_prompt="",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3,
        ):
            summary += token

        print(f"[TIMING agent:{self.persona_id}] _compress took {(time.perf_counter() - t0)*1000:.0f}ms", flush=True)
        return {"context_summary": summary, "messages": msgs[-2:]}

    # ── Edges ──────────────────────────────────────────────────────────────

    def _decide_complexity(self, state: AgentState) -> Literal["simple", "complex"]:
        return "simple" if state.get("complexity", "simple") == "simple" else "complex"

    def _check_context(self, state: AgentState) -> Literal["compress", "end"]:
        msgs = state.get("messages", [])
        total_chars = sum(len(m.content) for m in msgs if hasattr(m, "content"))
        if total_chars > settings.summary_trigger_tokens * 3:
            return "compress"
        return "end"

    # ── Helpers ────────────────────────────────────────────────────────────

    def _format_history(self, messages: list[BaseMessage]) -> str:
        lines = []
        for m in messages:
            role = "用户" if m.type == "human" else "助手"
            content = m.content[:200] if hasattr(m, "content") else str(m)[:200]
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(
        self, session_id: str, user_id: str, user_message: str,
        timeout: float = 180.0,
    ) -> str:
        config = {"configurable": {"thread_id": f"{session_id}_{self.persona_id}"}}

        initial_state: AgentState = {
            "messages": [HumanMessage(content=user_message)],
            "persona_id": self.persona_id,
            "persona_name": self.persona_name,
            "system_prompt": self.system_prompt,
            "session_id": session_id,
            "user_id": user_id,
            "retrieved_docs": [],
            "retrieval_query": "",
            "reasoning": "",
            "complexity": "simple",
            "context_summary": "",
            "tokens_used": 0,
            "final_response": "",
        }

        print(f"[DEBUG agent:{self.persona_id}] run() graph.ainvoke...", flush=True)
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.graph.ainvoke(initial_state, config),
                timeout=timeout,
            )
            print(f"[TIMING agent:{self.persona_id}] run() total={(time.perf_counter() - t0)*1000:.0f}ms complexity={result.get('complexity', '?')}", flush=True)
            return result.get("final_response", "")
        except asyncio.TimeoutError:
            print(f"[DEBUG agent:{self.persona_id}] run() TIMEOUT", flush=True)
            return f"[思考超时] {self.persona_name}思考时间过长，请稍后再试或简化问题。"

    async def resume(
        self, session_id: str, user_id: str, user_message: str,
        timeout: float = 180.0,
    ) -> str:
        print(f"[DEBUG agent:{self.persona_id}] resume() START", flush=True)
        config = {"configurable": {"thread_id": f"{session_id}_{self.persona_id}"}}

        ckpt_tuple = await self.checkpointer.aget_tuple(config)
        if ckpt_tuple:
            saved_channels = ckpt_tuple[1].get("channel_values", {})
            state = {
                "messages": saved_channels.get("messages", []),
                "persona_id": saved_channels.get("persona_id", self.persona_id),
                "persona_name": saved_channels.get("persona_name", self.persona_name),
                "system_prompt": saved_channels.get("system_prompt", self.system_prompt),
                "session_id": saved_channels.get("session_id", session_id),
                "user_id": user_id,
                "retrieved_docs": saved_channels.get("retrieved_docs", []),
                "retrieval_query": saved_channels.get("retrieval_query", ""),
                "reasoning": saved_channels.get("reasoning", ""),
                "complexity": saved_channels.get("complexity", "simple"),
                "context_summary": saved_channels.get("context_summary", ""),
                "tokens_used": saved_channels.get("tokens_used", 0),
                "final_response": saved_channels.get("final_response", ""),
            }
            state["messages"].append(HumanMessage(content=user_message))
        else:
            state = {
                "messages": [HumanMessage(content=user_message)],
                "persona_id": self.persona_id,
                "persona_name": self.persona_name,
                "system_prompt": self.system_prompt,
                "session_id": session_id,
                "user_id": user_id,
                "retrieved_docs": [],
                "retrieval_query": "",
                "reasoning": "",
                "complexity": "simple",
                "context_summary": "",
                "tokens_used": 0,
                "final_response": "",
            }

        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.graph.ainvoke(state, config),
                timeout=timeout,
            )
            print(f"[TIMING agent:{self.persona_id}] resume() total={(time.perf_counter() - t0)*1000:.0f}ms", flush=True)
            return result.get("final_response", "")
        except asyncio.TimeoutError:
            print(f"[DEBUG agent:{self.persona_id}] resume() TIMEOUT", flush=True)
            return f"[思考超时] {self.persona_name}思考时间过长，请稍后再试或简化问题。"
