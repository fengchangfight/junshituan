"""LangGraph-based agent template for advisor reasoning.

Streaming architecture:
- _reason outputs tagged format: <complexity> <reasoning> <response>
- StreamTagParser extracts <response> tokens on-the-fly
- token_callback passed via LangGraph config (NOT instance variable — avoids
  race conditions on the singleton agent instance)
- Result: user sees words stream in after TTFT

Session isolation:
- thread_id = {session_id}_{persona_id} — unique per session
- token_callback in config["configurable"] — request-scoped, never shared
- SqliteSaver persists checkpoints to disk — survives restarts

Graph:
  understand → retrieve → reason ──[simple]──→ END
                                    └──[complex]──→ respond → END
"""

import asyncio
import re
import time
from typing import TypedDict, Annotated, Literal, Optional, Callable, Awaitable

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.llm_client import chat_stream

# ── Persistent Checkpointer ──────────────────────────────────────────────


def _get_checkpointer() -> BaseCheckpointSaver:
    """Create a PostgresCheckpointer — stateless, safe to call repeatedly."""
    from app.services.agent.pg_checkpointer import PostgresCheckpointer
    return PostgresCheckpointer()

# ── Streaming Tag Parser ──────────────────────────────────────────────────

class StreamTagParser:
    """Parse XML-like tags from a streaming text source."""

    def __init__(self, tags: list[str]):
        self.tags = tags
        self.results: dict[str, str] = {t: "" for t in tags}
        self._buffer = ""
        self._current_tag: Optional[str] = None
        self._done_tags: set[str] = set()

    def feed(self, token: str) -> Optional[str]:
        """Feed a token. Returns text to forward (inside <response>), or None."""
        self._buffer += token
        if self._current_tag is None:
            return self._scan_for_open()
        else:
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
                    close_tag = f"</{tag}>"
                    end_idx = self._buffer.find(close_tag)
                    if end_idx >= 0:
                        content = self._buffer[:end_idx]
                        self.results[tag] = content
                        self._current_tag = None
                        self._done_tags.add(tag)
                        self._buffer = self._buffer[end_idx + len(close_tag):]
                        return content
                    return ""
                break
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
    """Base agent graph for an advisor.

    Thread-safe: token_callback is passed per-request via LangGraph config,
    never stored on the singleton instance. Safe for concurrent requests.
    """

    def __init__(
        self,
        persona_id: str,
        persona_name: str,
        system_prompt: str,
        retrieve_fn,
        checkpointer: Optional[BaseCheckpointSaver] = None,
    ):
        self.persona_id = persona_id
        self.persona_name = persona_name
        self.system_prompt = system_prompt
        self.retrieve_fn = retrieve_fn
        self.checkpointer = checkpointer or _get_checkpointer()
        self.graph = self._build()

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

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _get_callback(config: Optional[RunnableConfig]) -> Optional[Callable[[str], Awaitable[None]]]:
        """Extract token callback from LangGraph config. Thread-safe."""
        if config and "configurable" in config:
            return config["configurable"].get("token_callback")
        return None

    @staticmethod
    def _strip_tags(text: str) -> str:
        text = re.sub(r'<\s*/?\s*[a-zA-Z_][a-zA-Z0-9_]*\s*>', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @staticmethod
    def _extract_between(text: str, start: str, end: str) -> str:
        try:
            s = text.index(start) + len(start)
            e = text.index(end, s)
            return text[s:e].strip()
        except (ValueError, IndexError):
            return ""

    @staticmethod
    def _format_conversation(messages: list[BaseMessage], focus_turns: int = 2) -> str:
        """Format conversation history with recency weighting.

        Splits into two tiers:
        - Focus (last N turns): what the advisor should directly respond to
        - Background (older): for awareness only

        This prevents topic drift in multi-topic conversations — the LLM
        prioritizes the recent discussion without ignoring earlier context.
        """
        if not messages:
            return ""

        focus_count = focus_turns * 2  # Each turn = user msg + advisor msg

        if len(messages) <= focus_count:
            # Short history — all messages are focus
            lines = ["## 讨论上下文（请据此回应）"]
            for m in messages:
                if isinstance(m, HumanMessage):
                    lines.append(f"[用户]: {m.content[:500]}")
                else:
                    lines.append(m.content[:500])
            return "\n".join(lines) + "\n"

        # Split into background + focus
        background_msgs = messages[:-focus_count]
        focus_msgs = messages[-focus_count:]

        parts = []
        if background_msgs:
            parts.append("## 背景（此前的讨论，了解即可）")
            for m in background_msgs:
                if isinstance(m, HumanMessage):
                    parts.append(f"[用户]: {m.content[:300]}")
                else:
                    parts.append(m.content[:300])
            parts.append("")

        parts.append("## 最近讨论（请重点回应这部分）")
        for m in focus_msgs:
            if isinstance(m, HumanMessage):
                parts.append(f"[用户]: {m.content[:500]}")
            else:
                parts.append(m.content[:500])

        return "\n".join(parts) + "\n"

    def _format_history(self, messages: list[BaseMessage]) -> str:
        lines = []
        for m in messages:
            role = "用户" if m.type == "human" else "助手"
            content = m.content[:200] if hasattr(m, "content") else str(m)[:200]
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

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

    async def _reason(self, state: AgentState, config: RunnableConfig) -> dict:
        """Analyze + respond in one LLM call. Token callback from config (request-scoped)."""
        t0 = time.perf_counter()
        token_cb = self._get_callback(config)
        print(f"[DEBUG agent:{self.persona_id}] _reason START streaming={token_cb is not None}", flush=True)

        docs = state.get("retrieved_docs", [])
        docs_text = "\n---\n".join(docs[:5]) if docs else ""
        msgs = state.get("messages", [])

        # Build conversation context from ALL messages.
        # Uses recency-weighted split: recent = focus, older = background.
        question = msgs[-1].content if msgs else '无'
        conv_context = self._format_conversation(msgs[:-1])

        prompt = f"""{self.system_prompt}

## 参考资料
{docs_text if docs_text else '无相关参考资料'}

{conv_context}
## 当前发言
{question}

重要：请优先回应「最近讨论」中的话题。如果最近讨论切换了新话题，请围绕新话题展开，不要回到之前的旧话题。

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
2. 重点回应最近讨论的内容，回应前面军师的观点
3. response 150-400字，简洁有力
4. 可引用著作或名言，但点到为止"""

        print(f"[DEBUG agent:{self.persona_id}] _reason conv_msgs={len(msgs)-1} calling chat_stream...", flush=True)
        parser = StreamTagParser(["complexity", "reasoning", "response"])
        raw = ""
        async for token in chat_stream(
            system_prompt="",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
        ):
            raw += token
            forward = parser.feed(token)
            if forward and token_cb:
                await token_cb(forward)

        complexity = parser.results.get("complexity", "simple").strip()
        reasoning = parser.results.get("reasoning", "").strip()
        response = parser.results.get("response", "").strip()

        if not response:
            response = self._extract_between(raw, "<response>", "</response>")
            if not response:
                response = self._strip_tags(raw)
            complexity = "simple"

        response = self._strip_tags(response)

        print(f"[TIMING agent:{self.persona_id}] _reason took {(time.perf_counter() - t0)*1000:.0f}ms complexity={complexity} reasoning={len(reasoning)}chars response={len(response)}chars", flush=True)

        return {
            "reasoning": reasoning,
            "complexity": complexity,
            "final_response": response if complexity == "simple" else "",
        }

    async def _respond(self, state: AgentState, config: RunnableConfig) -> dict:
        """Polish final response for complex questions. Streams tokens directly."""
        t0 = time.perf_counter()
        token_cb = self._get_callback(config)
        print(f"[DEBUG agent:{self.persona_id}] _respond START (complex)", flush=True)

        reasoning = state.get("reasoning", "")
        docs = state.get("retrieved_docs", [])
        docs_text = "\n---\n".join(docs[:3]) if docs else ""
        msgs = state.get("messages", [])

        question = msgs[-1].content if msgs else ''
        conv_context = self._format_conversation(msgs[:-1])

        prompt = f"""{self.system_prompt}

## 前序分析
{reasoning}

## 参考资料
{docs_text if docs_text else '无'}

{conv_context}
## 当前发言
{question}

重要：请优先回应「最近讨论」中的话题。如果最近讨论切换了新话题，请围绕新话题展开。

请基于前序分析和讨论上下文，以{self.persona_name}的身份直接给出最终回答。
1. 第一人称，直接说话
2. 200-500字，有深度但不冗长
3. 重点回应最近讨论的观点"""

        print(f"[DEBUG agent:{self.persona_id}] _respond conv_msgs={len(msgs)-1} calling chat_stream...", flush=True)
        full = ""
        async for token in chat_stream(
            system_prompt="",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
        ):
            full += token
            if token_cb:
                await token_cb(token)

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

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(
        self, session_id: str, user_id: str, user_message: str,
        timeout: float = 180.0,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        history: Optional[list[dict]] = None,
    ) -> str:
        """Run agent for a single user message. Returns advisor's response.

        on_token: per-request streaming callback via config — thread-safe.
        history: optional conversation history for context injection.
        """
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"{session_id}_{self.persona_id}",
                "token_callback": on_token,
            }
        }

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

        print(f"[DEBUG agent:{self.persona_id}] run() session={session_id} streaming={on_token is not None}", flush=True)
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
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        history: Optional[list[dict]] = None,
    ) -> str:
        """Resume existing session with new user input.

        If this persona has a checkpoint for this session, loads from it.
        Otherwise builds context from the session's conversation history (DB).
        This ensures advisors joining mid-conversation see the full discussion.
        """
        print(f"[DEBUG agent:{self.persona_id}] resume() START session={session_id} has_history={history is not None}", flush=True)
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"{session_id}_{self.persona_id}",
                "token_callback": on_token,
            }
        }

        ckpt_tuple = await self.checkpointer.aget_tuple(config)
        if ckpt_tuple:
            print(f"[DEBUG agent:{self.persona_id}] resume() found checkpoint, loading...", flush=True)
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
            # No checkpoint — build context from session history.
            # Critical: new advisors joining mid-conversation need to see the
            # full discussion, not just the current system-generated prompt.
            messages = self._build_messages_from_history(history)
            messages.append(HumanMessage(content=user_message))
            state = {
                "messages": messages,
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

    @staticmethod
    def _build_messages_from_history(history: Optional[list[dict]]) -> list[BaseMessage]:
        """Convert DB message history to LangChain messages."""
        messages: list[BaseMessage] = []
        if not history:
            return messages
        for h in history:
            role = h.get("role", "")
            content = h.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            else:
                name = h.get("advisor_name", "")
                label = f"[{name}]: {content}" if name else content
                messages.append(AIMessage(content=label))
        return messages
