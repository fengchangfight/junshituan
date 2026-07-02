from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from app.core.config import settings


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
    stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=full_messages,
            temperature=temperature,
            stream=True,
        )
    print(f"[DEBUG llm] chat_stream request sent to {settings.openai_base_url} model={settings.llm_model}, waiting for chunks...", flush=True)

    usage = usage_out or StreamResult()

    async def token_gen() -> AsyncIterator[str]:
        try:
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                if chunk.usage:
                    usage.input_tokens = chunk.usage.prompt_tokens or 0
                    usage.output_tokens = chunk.usage.completion_tokens or 0
        except Exception as e:
            print(f"[DEBUG llm] chat_stream EXCEPTION: {type(e).__name__}: {e}", flush=True)
            raise

    async for token in token_gen():
        yield token


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
