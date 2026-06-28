"""Embedding provider — local (free) or OpenAI (API).

Dev:  LOCAL_EMBEDDING=true  → sentence-transformers + BGE-small-zh (512 dim)
Prod: LOCAL_EMBEDDING=false → OpenAI text-embedding-3-small (1536 dim)
"""

from typing import Optional

from app.core.config import settings

_local_model = None


class EmbeddingProvider:
    """Unified embedding interface."""

    def __init__(self):
        self._dim: Optional[int] = None
        self._ready = False

    async def ensure_ready(self):
        """Lazy init the embedding backend."""
        if self._ready:
            return

        if settings.local_embedding:
            await self._init_local()
        else:
            self._dim = 1536  # text-embedding-3-small
        self._ready = True

    async def _init_local(self):
        global _local_model
        if _local_model is None:
            import asyncio
            loop = asyncio.get_event_loop()
            _local_model = await loop.run_in_executor(None, self._load_model)
        self._dim = _local_model.get_sentence_embedding_dimension()

    def _load_model(self):
        from sentence_transformers import SentenceTransformer
        print(f"Loading local embedding model: {settings.local_embedding_model} ...")
        model = SentenceTransformer(settings.local_embedding_model)
        print(f"  → dim={model.get_sentence_embedding_dimension()}")
        return model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of vectors."""
        await self.ensure_ready()

        if settings.local_embedding:
            return await self._embed_local(texts)
        else:
            return await self._embed_openai(texts)

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text. Returns one vector."""
        results = await self.embed([text])
        return results[0]

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, lambda: _local_model.encode(texts, normalize_embeddings=True).tolist()
        )
        return embeddings

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.embedding_api_key or settings.openai_api_key,
            base_url=settings.embedding_base_url,
        )
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [d.embedding for d in resp.data]

    @property
    def dim(self) -> int:
        if self._dim is None:
            return settings.embedding_dim
        return self._dim


embedding_provider = EmbeddingProvider()
