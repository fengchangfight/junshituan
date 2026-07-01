"""Embedding provider — ZhipuAI embedding-2 via OpenAI-compatible API."""

from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings


def _make_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.embedding_api_key or settings.openai_api_key,
        base_url=settings.embedding_base_url,
        timeout=60.0,
    )


class EmbeddingProvider:
    """Embedding interface backed by ZhipuAI embedding-2.

    Uses OpenAI-compatible API format. Dimension: 1024.
    """

    def __init__(self):
        self._dim: Optional[int] = None
        self._ready = False

    async def _ensure_ready(self):
        if self._ready:
            return
        try:
            client = _make_client()
            resp = await client.embeddings.create(
                model=settings.embedding_model,
                input=["test"],
            )
            self._dim = len(resp.data[0].embedding)
            print(f"Embedding ready: {settings.embedding_model}, dim={self._dim}")
        except Exception as e:
            print(f"WARNING: embedding init failed ({e}), using config dim={settings.embedding_dim}")
            self._dim = settings.embedding_dim
        self._ready = True

    async def embed(self, texts: list[str]) -> list[list[float]]:
        await self._ensure_ready()
        client = _make_client()
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [d.embedding for d in resp.data]

    async def embed_single(self, text: str) -> list[float]:
        await self._ensure_ready()
        client = _make_client()
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=[text],
        )
        return resp.data[0].embedding

    async def ensure_ready(self):
        await self._ensure_ready()

    @property
    def dim(self) -> int:
        if self._dim is None:
            return settings.embedding_dim
        return self._dim

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous embed — for use in llama-index pipeline (runs in executor)."""
        import asyncio
        return asyncio.run(self.embed(texts))


embedding_provider = EmbeddingProvider()

