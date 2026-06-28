from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from app.core.config import settings

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
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
) -> AsyncIterator[str]:
    """Stream chat completion. Pass usage_out to capture token counts."""
    full_messages = [{"role": "system", "content": system_prompt}, *messages]

    stream = await _get_client().chat.completions.create(
        model=settings.llm_model,
        messages=full_messages,
        temperature=temperature,
        stream=True,
        stream_options={"include_usage": True},
    )

    usage = usage_out or StreamResult()

    async def token_gen() -> AsyncIterator[str]:
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
            if chunk.usage:
                usage.input_tokens = chunk.usage.prompt_tokens or 0
                usage.output_tokens = chunk.usage.completion_tokens or 0

    async for token in token_gen():
        yield token


async def get_embedding(text: str) -> tuple[list[float], int]:
    """Get embedding vector. Returns (embedding, tokens_used)."""
    response = await _get_client().embeddings.create(
        model=settings.embedding_model,
        input=[text],
    )
    tokens = response.usage.total_tokens if response.usage else len(text) // 3
    return response.data[0].embedding, tokens
