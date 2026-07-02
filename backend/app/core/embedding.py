"""Embedding provider — ZhipuAI embedding-2 via OpenAI-compatible API."""

from typing import Optional

from openai import AsyncOpenAI, OpenAI

from app.core.config import settings


def _make_async_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.embedding_api_key or settings.openai_api_key,
        base_url=settings.embedding_base_url,
        timeout=60.0,
    )


def _make_sync_client() -> OpenAI:
    return OpenAI(
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
            client = _make_async_client()
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
        client = _make_async_client()
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [d.embedding for d in resp.data]

    async def embed_single(self, text: str) -> list[float]:
        print(f"[DEBUG embed] embed_single START text_len={len(text)}", flush=True)
        await self._ensure_ready()
        client = _make_async_client()
        print(f"[DEBUG embed] embed_single calling {settings.embedding_base_url} model={settings.embedding_model}...", flush=True)
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=[text],
        )
        emb = resp.data[0].embedding
        print(f"[DEBUG embed] embed_single DONE dim={len(emb)}", flush=True)
        return emb

    async def ensure_ready(self):
        await self._ensure_ready()

    @property
    def dim(self) -> int:
        if self._dim is None:
            return settings.embedding_dim
        return self._dim

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous embed — for llama-index pipeline (runs in executor thread)."""
        client = _make_sync_client()
        # Filter out empty/whitespace-only texts
        clean = [t for t in texts if t.strip()]
        if not clean:
            return []
        # Batch in groups of 8 to avoid request size limits
        all_embeddings = []
        for i in range(0, len(clean), 8):
            batch = clean[i:i + 8]
            resp = client.embeddings.create(
                model=settings.embedding_model,
                input=batch,
                extra_body={"encoding_format": "float"},
            )
            all_embeddings.extend([d.embedding for d in resp.data])
        return all_embeddings


embedding_provider = EmbeddingProvider()


