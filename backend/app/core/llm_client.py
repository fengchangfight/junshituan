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


async def chat_stream(
    system_prompt: str,
    messages: list[dict[str, str]],
    temperature: float = 0.8,
) -> AsyncIterator[str]:
    full_messages = [{"role": "system", "content": system_prompt}, *messages]

    stream = await _get_client().chat.completions.create(
        model=settings.llm_model,
        messages=full_messages,
        temperature=temperature,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


async def get_embedding(text: str) -> list[float]:
    response = await _get_client().embeddings.create(
        model=settings.embedding_model,
        input=[text],
    )
    return response.data[0].embedding
