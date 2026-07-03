import time
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("llm")


_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=120.0,
        )
    return _client


@dataclass
class StreamResult:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


async def chat_stream(
    system_prompt: str,
    messages: list[dict[str, str]],
    temperature: float = 0.8,
    usage_out: Optional[StreamResult] = None,
    timeout: float = 120.0,
) -> AsyncIterator[str]:
    """Stream chat completion. Pass usage_out to capture token counts."""
    full_messages: list[dict[str, str]] = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=timeout,
    )
    t_start = time.perf_counter()
    stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=full_messages,
            temperature=temperature,
            stream=True,
        )
    log.debug(f"chat_stream request sent to {settings.openai_base_url} model={settings.llm_model}, waiting for chunks...")

    usage = usage_out or StreamResult()
    first_token = True

    async def token_gen() -> AsyncIterator[str]:
        nonlocal first_token
        try:
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        if first_token:
                            first_token = False
                            log.timing(f"TTFT={(time.perf_counter() - t_start)*1000:.0f}ms")
                        yield delta.content
                if chunk.usage:
                    usage.input_tokens = chunk.usage.prompt_tokens or 0
                    usage.output_tokens = chunk.usage.completion_tokens or 0
        except Exception as e:
            log.debug(f"chat_stream EXCEPTION: {type(e).__name__}: {e}")
            raise

    async for token in token_gen():
        yield token
    log.timing(f"chat_stream total={(time.perf_counter() - t_start)*1000:.0f}ms input_tokens={usage.input_tokens} output_tokens={usage.output_tokens}")


async def chat(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
) -> str:
    """Non-streaming chat completion. Returns the full response text."""
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    response = await _get_client().chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


@dataclass
class ToolCallResult:
    """Result from a chat completion that may include tool calls."""

    content: str | None = None
    tool_calls: list[dict] | None = None
    """Each tool_call: {"id": str, "name": str, "arguments": dict}"""


async def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    temperature: float = 0.7,
    model: str | None = None,
) -> ToolCallResult:
    """Chat completion with tool/function calling support.

    Returns either a text response or a list of tool calls (not both).
    Caller should:
      - If tool_calls: execute them, append results as messages, call again.
      - If content: the final response is ready.
    """
    response = await _get_client().chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        tools=tools,
        temperature=temperature,
    )
    msg = response.choices[0].message

    if msg.tool_calls:
        tool_calls = []
        for tc in msg.tool_calls:
            import json as _json
            try:
                args = _json.loads(tc.function.arguments)
            except _json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": args,
            })
        return ToolCallResult(tool_calls=tool_calls)

    return ToolCallResult(content=msg.content or "")


async def chat_with_tools_stream(
    messages: list[dict],
    tools: list[dict],
    temperature: float = 0.7,
    model: str | None = None,
    token_cb=None,
) -> ToolCallResult:
    """Streaming chat with tool/function calling support.

    Streams text tokens via token_cb in real-time. When the model emits
    tool_calls, those are accumulated across chunks and returned without
    streaming any text (tool calls precede content).
    """
    stream = await _get_client().chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        tools=tools,
        temperature=temperature,
        stream=True,
    )

    tool_calls_acc: dict[int, dict] = {}
    content_parts: list[str] = []
    has_tool_calls = False

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        if delta.tool_calls:
            has_tool_calls = True
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = {
                        "id": tc_delta.id or "",
                        "function": {"name": "", "arguments": ""},
                    }
                acc = tool_calls_acc[idx]
                if tc_delta.id:
                    acc["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        acc["function"]["name"] += tc_delta.function.name
                    if tc_delta.function.arguments:
                        acc["function"]["arguments"] += tc_delta.function.arguments

        if delta.content:
            content_parts.append(delta.content)
            if token_cb and not has_tool_calls:
                await token_cb(delta.content)

    if has_tool_calls and tool_calls_acc:
        import json as _json
        tool_calls = []
        for idx in sorted(tool_calls_acc.keys()):
            tc = tool_calls_acc[idx]
            try:
                args = _json.loads(tc["function"]["arguments"])
            except _json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc["id"],
                "name": tc["function"]["name"],
                "arguments": args,
            })
        return ToolCallResult(tool_calls=tool_calls)

    return ToolCallResult(content="".join(content_parts))
