"""LangGraph-based agent template for advisor reasoning.

Design philosophy (inspired by Claude Code sub-agents):
- Each advisor agent is a LangGraph state machine
- Agents can dispatch sub-agents for complex sub-tasks
- State is checkpointed for session resume
- Context is managed with compression and sliding windows
"""

import asyncio
import json
from typing import TypedDict, Annotated, Literal, Optional
from datetime import datetime, timezone

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.core.config import settings
from app.core.llm_client import chat_stream


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

    # Reasoning chain
    reasoning: str
    sub_tasks: list[dict]

    # Context management
    context_summary: str
    tokens_used: int

    # Final output
    final_response: str
    needs_sub_agent: bool
    sub_agent_task: str


# ── Agent Graph Builder ────────────────────────────────────────────────────

class AdvisorAgentGraph:
    """Base agent graph for an advisor.

    Each advisor persona instantiates this with:
    - persona-specific system_prompt
    - persona-specific knowledge retrieval function
    - persona-specific sub-agent spawning logic
    """

    def __init__(
        self,
        persona_id: str,
        persona_name: str,
        system_prompt: str,
        retrieve_fn,  # async (query: str) -> list[str]
        sub_agent_fn=None,  # async (task: str, context: str) -> str
        checkpointer: Optional[BaseCheckpointSaver] = None,
    ):
        self.persona_id = persona_id
        self.persona_name = persona_name
        self.system_prompt = system_prompt
        self.retrieve_fn = retrieve_fn
        self.sub_agent_fn = sub_agent_fn
        self.checkpointer = checkpointer or MemorySaver()
        self.graph = self._build()

    def _build(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        workflow.add_node("understand", self._understand)
        workflow.add_node("retrieve", self._retrieve)
        workflow.add_node("reason", self._reason)
        workflow.add_node("sub_agent", self._run_sub_agent)
        workflow.add_node("respond", self._respond)
        workflow.add_node("compress", self._compress)

        workflow.add_edge(START, "understand")
        workflow.add_edge("understand", "retrieve")
        workflow.add_edge("retrieve", "reason")

        workflow.add_conditional_edges(
            "reason",
            self._decide_next,
            {
                "sub_agent": "sub_agent",
                "respond": "respond",
            },
        )

        workflow.add_edge("sub_agent", "respond")

        workflow.add_conditional_edges(
            "respond",
            self._check_context,
            {
                "compress": "compress",
                "end": END,
            },
        )

        workflow.add_edge("compress", END)

        return workflow.compile(checkpointer=self.checkpointer)

    # ── Node implementations ────────────────────────────────────────────────

    async def _understand(self, state: AgentState) -> dict:
        """Parse the user's question and determine what knowledge is needed."""
        msgs = state.get("messages", [])
        last_msg = msgs[-1].content if msgs else ""
        return {
            "retrieval_query": last_msg,
            "reasoning": "",
        }

    async def _retrieve(self, state: AgentState) -> dict:
        """Retrieve relevant knowledge from the advisor's corpus."""
        print(f"[DEBUG agent:{self.persona_id}] _retrieve START", flush=True)
        query = state.get("retrieval_query", "")
        if self.retrieve_fn and query:
            print(f"[DEBUG agent:{self.persona_id}] _retrieve calling retrieve_fn...", flush=True)
            docs = await self.retrieve_fn(query)
            print(f"[DEBUG agent:{self.persona_id}] _retrieve got {len(docs)} docs", flush=True)
            return {"retrieved_docs": docs}
        print(f"[DEBUG agent:{self.persona_id}] _retrieve skipped (no query or retrieve_fn)", flush=True)
        return {"retrieved_docs": []}

    async def _reason(self, state: AgentState) -> dict:
        """Core reasoning step: analyze with persona's thinking framework."""
        print(f"[DEBUG agent:{self.persona_id}] _reason START", flush=True)
        docs = state.get("retrieved_docs", [])
        docs_text = "\n---\n".join(docs[:5]) if docs else ""

        msgs = state.get("messages", [])
        current_question = msgs[-1].content if msgs else '无'

        reasoning_prompt = f"""{self.system_prompt}

## 当前问题
{current_question}

## 检索到的参考资料
{docs_text if docs_text else '无相关参考资料'}

## 任务
请你以{self.persona_name}的思维方式进行推理分析。输出JSON格式：

```json
{{
  "reasoning": "你的推理过程",
  "needs_sub_agent": false,
  "sub_agent_task": "",
  "preliminary_answer": "你的初步回答"
}}
```

如果问题涉及复杂计算、需要外部信息验证、或者需要分步骤深入分析某个子问题，设置needs_sub_agent为true并描述子任务。"""

        print(f"[DEBUG agent:{self.persona_id}] _reason calling chat_stream...", flush=True)
        reasoning = ""
        async for token in chat_stream(
            system_prompt="",
            messages=[{"role": "user", "content": reasoning_prompt}],
            temperature=0.7,
        ):
            reasoning += token
        print(f"[DEBUG agent:{self.persona_id}] _reason chat_stream done, len={len(reasoning)}", flush=True)

        parsed = self._parse_json(reasoning)
        return {
            "reasoning": parsed.get("reasoning", reasoning),
            "needs_sub_agent": parsed.get("needs_sub_agent", False),
            "sub_agent_task": parsed.get("sub_agent_task", ""),
        }

    async def _run_sub_agent(self, state: AgentState) -> dict:
        """Dispatch a sub-agent for a complex sub-task."""
        task = state.get("sub_agent_task", "")
        if self.sub_agent_fn and task:
            context = state.get("reasoning", "")
            result = await self.sub_agent_fn(task, context)
            return {"reasoning": state.get("reasoning", "") + f"\n\n[子分析结果]\n{result}"}
        return {}

    async def _respond(self, state: AgentState) -> dict:
        """Generate the final response in the advisor's voice."""
        print(f"[DEBUG agent:{self.persona_id}] _respond START", flush=True)
        reasoning = state.get("reasoning", "")
        docs = state.get("retrieved_docs", [])
        docs_text = "\n---\n".join(docs[:3]) if docs else ""
        msgs = state.get("messages", [])

        response_prompt = f"""{self.system_prompt}

## 推理分析
{reasoning}

## 参考资料
{docs_text if docs_text else '无'}

## 用户问题
{msgs[-1].content if msgs else ''}

请以{self.persona_name}的身份和语言风格，给出最终回答。注意：
1. 你是{self.persona_name}本人，直接说话
2. 可以引用自己的著作或名言
3. 保持谦逊但坚定
4. 简洁有力"""

        print(f"[DEBUG agent:{self.persona_id}] _respond calling chat_stream...", flush=True)
        full_response = ""
        async for token in chat_stream(
            system_prompt="",
            messages=[{"role": "user", "content": response_prompt}],
            temperature=0.85,
        ):
            full_response += token
        print(f"[DEBUG agent:{self.persona_id}] _respond chat_stream done, len={len(full_response)}", flush=True)

        return {"final_response": full_response}

    async def _compress(self, state: AgentState) -> dict:
        """Compress context when approaching token limits."""
        msgs = state.get("messages", [])
        if len(msgs) <= 4:
            return {}

        summary_prompt = f"""请将以下对话历史压缩为一段简洁的摘要，保留关键信息和决策：

{self._format_history(msgs[:-2])}

摘要："""

        summary = ""
        async for token in chat_stream(
            system_prompt="",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3,
        ):
            summary += token

        return {
            "context_summary": summary,
            "messages": msgs[-2:],  # Keep last 2 messages
        }

    # ── Edge logic ──────────────────────────────────────────────────────────

    def _decide_next(self, state: AgentState) -> Literal["sub_agent", "respond"]:
        if state.get("needs_sub_agent") and self.sub_agent_fn:
            return "sub_agent"
        return "respond"

    def _check_context(self, state: AgentState) -> Literal["compress", "end"]:
        msgs = state.get("messages", [])
        total_chars = sum(len(m.content) for m in msgs if hasattr(m, "content"))
        if total_chars > settings.summary_trigger_tokens * 3:  # rough char estimate
            return "compress"
        return "end"

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _parse_json(self, text: str) -> dict:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {}

    def _format_history(self, messages: list[BaseMessage]) -> str:
        lines = []
        for m in messages:
            role = "用户" if m.type == "human" else "助手"
            content = m.content[:200] if hasattr(m, "content") else str(m)[:200]
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        timeout: float = 180.0,
    ) -> str:
        """Run the agent for a single user message. Returns the advisor's response."""
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
            "sub_tasks": [],
            "context_summary": "",
            "tokens_used": 0,
            "final_response": "",
            "needs_sub_agent": False,
            "sub_agent_task": "",
        }

        print(f"[DEBUG agent:{self.persona_id}] run() calling graph.ainvoke with timeout={timeout}...", flush=True)
        try:
            result = await asyncio.wait_for(
                self.graph.ainvoke(initial_state, config),
                timeout=timeout,
            )
            print(f"[DEBUG agent:{self.persona_id}] run() graph.ainvoke DONE", flush=True)
            return result.get("final_response", "")
        except asyncio.TimeoutError:
            print(f"[DEBUG agent:{self.persona_id}] run() TIMEOUT after {timeout}s", flush=True)
            return f"[思考超时] {self.persona_name}思考时间过长，请稍后再试或简化问题。"

    async def resume(
        self,
        session_id: str,
        user_id: str,
        user_message: str,
        timeout: float = 180.0,
    ) -> str:
        """Resume an existing session with new user input."""
        print(f"[DEBUG agent:{self.persona_id}] resume() START session={session_id}", flush=True)
        config = {"configurable": {"thread_id": f"{session_id}_{self.persona_id}"}}

        # Load existing state from checkpointer
        ckpt_tuple = await self.checkpointer.aget_tuple(config)
        if ckpt_tuple:
            print(f"[DEBUG agent:{self.persona_id}] resume() found checkpoint", flush=True)
            # CheckpointTuple = (config, checkpoint, metadata, parent_config)
            # checkpoint is a dict with "channel_values" containing the state
            saved_channels = ckpt_tuple[1].get("channel_values", {})
            # Merge saved channels into a fresh state, then add new message
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
                "sub_tasks": saved_channels.get("sub_tasks", []),
                "context_summary": saved_channels.get("context_summary", ""),
                "tokens_used": saved_channels.get("tokens_used", 0),
                "final_response": saved_channels.get("final_response", ""),
                "needs_sub_agent": saved_channels.get("needs_sub_agent", False),
                "sub_agent_task": saved_channels.get("sub_agent_task", ""),
            }
            state["messages"].append(HumanMessage(content=user_message))
        else:
            print(f"[DEBUG agent:{self.persona_id}] resume() no checkpoint, fresh start", flush=True)
            # Fallback to fresh start
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
                "sub_tasks": [],
                "context_summary": "",
                "tokens_used": 0,
                "final_response": "",
                "needs_sub_agent": False,
                "sub_agent_task": "",
            }

        print(f"[DEBUG agent:{self.persona_id}] resume() calling graph.ainvoke...", flush=True)
        try:
            result = await asyncio.wait_for(
                self.graph.ainvoke(state, config),
                timeout=timeout,
            )
            print(f"[DEBUG agent:{self.persona_id}] resume() graph.ainvoke DONE", flush=True)
            return result.get("final_response", "")
        except asyncio.TimeoutError:
            print(f"[DEBUG agent:{self.persona_id}] resume() TIMEOUT after {timeout}s", flush=True)
            return f"[思考超时] {self.persona_name}思考时间过长，请稍后再试或简化问题。"
