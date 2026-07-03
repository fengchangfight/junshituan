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
- PostgresCheckpointer persists checkpoints to database — survives restarts

Graph:
  understand → retrieve → reason ──[simple]──→ END
                                    └──[complex]──→ respond → END
"""

import asyncio
import contextvars
import re
import time
from typing import TypedDict, Annotated, Literal, Optional, Callable, Awaitable

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from app.core.logging import get_logger

log = get_logger("agent")

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

    # Tool calling (ReAct loop)
    pending_tool_calls: list[dict]  # tool calls the LLM wants to make
    tool_messages: list[dict]       # accumulated assistant(tool_calls) + tool results
    tool_rounds: int                # counter to prevent infinite loops

    # Final output
    final_response: str

MAX_TOOL_ROUNDS = 2  # the second round is for the fill response, not tool loops

# Context vars for request-scoped callbacks (async-safe, survives LangGraph node routing)
_ctx_tool_callback: contextvars.ContextVar[Optional[Callable[[dict], Awaitable[None]]]] = \
    contextvars.ContextVar("tool_callback", default=None)


# ── Agent Graph Builder ────────────────────────────────────────────────────

class AdvisorAgentGraph:
    """Base agent graph for an advisor.

    Thread-safe: token_callback and tool_callback are passed per-request via LangGraph config,
    never stored on the singleton instance. Safe for concurrent requests.
    Note: tool_callback is also stored on the instance as an implementation detail
    because LangGraph node routing can lose the config reference.
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
        workflow.add_node("tool_call", self._tool_call)
        workflow.add_node("respond", self._respond)
        workflow.add_node("compress", self._compress)

        workflow.add_edge(START, "understand")
        workflow.add_edge("understand", "retrieve")
        workflow.add_edge("retrieve", "reason")

        # Reason → tool loop or complexity decision
        workflow.add_conditional_edges(
            "reason",
            self._after_reason,
            {"tool_call": "tool_call", "simple": END, "complex": "respond"},
        )

        # Tool call → back to reason (ReAct loop)
        workflow.add_edge("tool_call", "reason")

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
    def _get_tool_callback(config: Optional[RunnableConfig]) -> Optional[Callable[[dict], Awaitable[None]]]:
        """Extract tool progress callback from LangGraph config."""
        if config and "configurable" in config:
            return config["configurable"].get("tool_callback")
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
        log.timing(f"_understand took {(time.perf_counter() - t0)*1000:.0f}ms")
        return {"retrieval_query": last_msg}

    async def _retrieve(self, state: AgentState) -> dict:
        t0 = time.perf_counter()
        query = state.get("retrieval_query", "")
        if self.retrieve_fn and query:
            log.debug(f"_retrieve calling retrieve_fn...")
            docs = await self.retrieve_fn(query)
            log.timing(f"_retrieve took {(time.perf_counter() - t0)*1000:.0f}ms, got {len(docs)} docs")
            return {"retrieved_docs": docs}
        log.timing(f"_retrieve skipped {(time.perf_counter() - t0)*1000:.0f}ms")
        return {"retrieved_docs": []}

    async def _reason(self, state: AgentState, config: RunnableConfig) -> dict:
        """Analyze + respond. Uses tool calling if tools are available, falls back
        to prompt-based reasoning otherwise. Token callback from config."""
        t0 = time.perf_counter()
        token_cb = self._get_callback(config)
        rounds = state.get("tool_rounds", 0)
        log.timing(f"_reason ENTER streaming={token_cb is not None} rounds={rounds}")

        docs = state.get("retrieved_docs", [])
        docs_text = "\n---\n".join(docs[:5]) if docs else ""
        msgs = state.get("messages", [])
        question = msgs[-1].content if msgs else "无"

        # Build message list for tool-calling API
        conv_context = self._format_conversation(msgs[:-1])
        full_prompt = f"""{self.system_prompt}

## 参考资料
{docs_text if docs_text else '无相关参考资料'}
{conv_context}
## 当前发言
{question}

重要：请优先回应「最近讨论」中的话题。

## 格式要求
- 用纯文本回复，不要使用markdown格式（不要用 # * - 等符号）
- 你是{self.persona_name}本人，用第一人称直接说话
- 回答150-400字，简洁有力，可引用著作或名言但点到为止
- 如果使用了搜索工具，请在回答末尾注明信息来源"""

        # ── Tool-calling path ────────────────────────────────────────────────
        from app.tools import tool_registry
        tools = tool_registry.get_schemas()
        rounds = state.get("tool_rounds", 0)
        tool_msgs: list[dict] = list(state.get("tool_messages") or [])

        if tools and rounds < MAX_TOOL_ROUNDS:
            # Build messages array for the API
            api_messages: list[dict] = [
                {"role": "system", "content": full_prompt},
            ]

            # Splice in prior tool messages (assistant tool_calls + tool results)
            api_messages.extend(tool_msgs)
            log.debug(f"_reason re-entry: tool_msgs={len(tool_msgs)} rounds={rounds}")

            # Append the actual user question
            api_messages.append({"role": "user", "content": question})

            # Signal frontend early — avoid staring at "thinking..." for TTFT
            if rounds == 0 and token_cb:
                await token_cb("📚")

            from app.core.llm_client import chat_with_tools

            t_llm = time.perf_counter()
            result = await chat_with_tools(
                messages=api_messages,
                tools=tools,
                temperature=0.85,
            )

            if result.tool_calls:
                log.timing(f"_reason LLM decided tool_calls={[tc['name'] for tc in result.tool_calls]} in {(time.perf_counter()-t_llm)*1000:.0f}ms")
                import json as _json
                # Build assistant message; splice into tool_messages later with results
                tool_asm: dict = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": _json.dumps(tc.get("arguments", {}), ensure_ascii=False),
                            },
                        }
                        for tc in result.tool_calls
                    ],
                }
                return {
                    "pending_tool_calls": result.tool_calls,
                    "tool_messages": [tool_asm],
                    "reasoning": "",
                    "complexity": "simple",
                }

            # Got a text response — parse it for tags
            if result.content:
                raw = result.content
            else:
                raw = ""
        else:
            # ── No tools / max rounds — fall back to streaming prompt path ──
            prompt = f"""{full_prompt}

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
complexity=simple（多数情况）：日常问答、观点表达、知识介绍。
complexity=complex：需要多步推理、对比分析、数学计算。

### 要求
1. 你是{self.persona_name}本人，response用第一人称直接说话
2. 重点回应最近讨论的内容，回应前面军师的观点
3. response 150-400字，简洁有力
4. 可引用著作或名言，但点到为止"""

            log.debug(f"_reason conv_msgs={len(msgs)-1} calling chat_stream...")
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

        # ── Parse response ───────────────────────────────────────────────────
        complexity = "simple"
        reasoning = ""
        response = ""

        if raw:
            # Try tag extraction
            c_match = re.search(r"<complexity>(.*?)</complexity>", raw, re.DOTALL)
            if c_match:
                complexity = c_match.group(1).strip()
            r_match = re.search(r"<reasoning>(.*?)</reasoning>", raw, re.DOTALL)
            if r_match:
                reasoning = r_match.group(1).strip()
            resp_match = re.search(r"<response>(.*?)</response>", raw, re.DOTALL)
            if resp_match:
                response = resp_match.group(1).strip()

            if not response:
                response = self._strip_tags(raw)
                complexity = "simple"

        response = self._strip_tags(response)

        if response and tools and rounds < MAX_TOOL_ROUNDS and token_cb:
            import asyncio
            for i in range(0, len(response), 2):
                await token_cb(response[i:i+2])
                await asyncio.sleep(0.015)

        log.timing(f"_reason took {(time.perf_counter() - t0)*1000:.0f}ms complexity={complexity} response={len(response)}chars rounds={rounds}")

        return {
            "reasoning": reasoning,
            "complexity": complexity,
            "tool_messages": [],
            "pending_tool_calls": [],
            "tool_rounds": 0,
            "final_response": response if complexity == "simple" else "",
        }

    async def _respond(self, state: AgentState, config: RunnableConfig) -> dict:
        """Polish final response for complex questions. Streams tokens directly."""
        t0 = time.perf_counter()
        token_cb = self._get_callback(config)
        log.debug(f"_respond START (complex)")

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

        log.debug(f"_respond conv_msgs={len(msgs)-1} calling chat_stream...")
        full = ""
        async for token in chat_stream(
            system_prompt="",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
        ):
            full += token
            if token_cb:
                await token_cb(token)

        log.timing(f"_respond took {(time.perf_counter() - t0)*1000:.0f}ms response={len(full)}chars")
        return {"final_response": full}

    async def _compress(self, state: AgentState) -> dict:
        t0 = time.perf_counter()
        log.timing(f"_compress START")
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

        log.timing(f"_compress took {(time.perf_counter() - t0)*1000:.0f}ms")
        return {"context_summary": summary, "messages": msgs[-2:]}

    # ── Edges ──────────────────────────────────────────────────────────────

    def _after_reason(self, state: AgentState) -> Literal["tool_call", "simple", "complex"]:
        """Route after _reason: tool loop or complexity decision."""
        pending = state.get("pending_tool_calls") or []
        if pending:
            return "tool_call"
        complexity = state.get("complexity", "simple")
        return "simple" if complexity == "simple" else "complex"

    async def _tool_call(self, state: AgentState, config: RunnableConfig) -> dict:
        """Execute pending tool calls and collect results.
        Emits progress via tool_callback so the frontend can show live status.
        Appends tool result messages to tool_messages for API conversation history.
        """
        from app.tools import tool_registry

        pending = state.get("pending_tool_calls") or []
        rounds = state.get("tool_rounds", 0)
        tool_msgs: list[dict] = list(state.get("tool_messages") or [])
        tool_cb = self._get_tool_callback(config) or _ctx_tool_callback.get()
        log.debug(f"_tool_call tool_cb={'SET' if tool_cb else 'NONE'} pending={len(pending)}")

        for tc in pending:
            name = tc["name"]
            args = tc.get("arguments", {})
            call_id = tc.get("id", "")
            log.debug(f"_tool_call executing {name} id={call_id}")

            # Notify frontend: search starting
            if tool_cb:
                await tool_cb({
                    "action": "tool_start",
                    "tool_name": name,
                    "query": args.get("query", ""),
                })

            res = await tool_registry.execute(name, args)
            result_count = len(res.data.get("results", [])) if res.data else 0
            content_preview = res.content[:80].replace("\n", " ") if res.content else "(empty)"
            log.debug(f"_tool_call DONE {name} results={result_count} content={content_preview}")

            # Notify frontend: search done
            if tool_cb:
                result_items = []
                if res.data and res.data.get("results"):
                    for r in res.data["results"][:5]:
                        result_items.append({
                            "title": r.get("title", "")[:100],
                            "href": r.get("href", ""),
                            "snippet": r.get("body", "")[:150],
                        })
                await tool_cb({
                    "action": "tool_done",
                    "tool_name": name,
                    "query": args.get("query", ""),
                    "result_count": len(res.data.get("results", [])) if res.data else 0,
                    "results": result_items,
                })

            # Append tool result message (must follow assistant tool_calls message)
            tool_msgs.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": res.content,
            })

        return {
            "pending_tool_calls": [],
            "tool_messages": tool_msgs,
            "tool_rounds": rounds + 1,
        }

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
        on_tool_progress: Optional[Callable[[dict], Awaitable[None]]] = None,
        history: Optional[list[dict]] = None,
    ) -> str:
        """Run agent for a single user message. Returns advisor's response.

        on_token: per-request streaming callback via config — thread-safe.
        on_tool_progress: callback for tool execution progress events.
        history: optional conversation history for context injection.
        """
        _ctx_tool_callback.set(on_tool_progress)
        log.debug(f"run() tool_cb={'SET' if on_tool_progress else 'NONE'}")
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"{session_id}_{self.persona_id}",
                "token_callback": on_token,
                "tool_callback": on_tool_progress,
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
            "pending_tool_calls": [],
            "tool_messages": [],
            "tool_rounds": 0,
            "final_response": "",
        }

        log.debug(f"run() session={session_id} streaming={on_token is not None}")
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.graph.ainvoke(initial_state, config),
                timeout=timeout,
            )
            log.timing(f"run() total={(time.perf_counter() - t0)*1000:.0f}ms complexity={result.get('complexity', '?')}")
            return result.get("final_response", "")
        except asyncio.TimeoutError:
            log.debug(f"run() TIMEOUT")
            return f"[思考超时] {self.persona_name}思考时间过长，请稍后再试或简化问题。"

    async def resume(
        self, session_id: str, user_id: str, user_message: str,
        timeout: float = 180.0,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_tool_progress: Optional[Callable[[dict], Awaitable[None]]] = None,
        history: Optional[list[dict]] = None,
    ) -> str:
        """Resume existing session with new user input.

        If this persona has a checkpoint for this session, loads from it.
        Otherwise builds context from the session's conversation history (DB).
        This ensures advisors joining mid-conversation see the full discussion.
        """
        log.debug(f"resume() START session={session_id} has_history={history is not None}")
        _ctx_tool_callback.set(on_tool_progress)
        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"{session_id}_{self.persona_id}",
                "token_callback": on_token,
                "tool_callback": on_tool_progress,
            }
        }

        ckpt_tuple = await self.checkpointer.aget_tuple(config)
        if ckpt_tuple:
            log.debug(f"resume() found checkpoint, loading...")
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
                "pending_tool_calls": [],
                "tool_messages": [],
                "tool_rounds": 0,
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
                "pending_tool_calls": [],
                "tool_messages": [],
                "tool_rounds": 0,
                "final_response": "",
            }

        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.graph.ainvoke(state, config),
                timeout=timeout,
            )
            log.timing(f"resume() total={(time.perf_counter() - t0)*1000:.0f}ms")
            return result.get("final_response", "")
        except asyncio.TimeoutError:
            log.debug(f"resume() TIMEOUT")
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
