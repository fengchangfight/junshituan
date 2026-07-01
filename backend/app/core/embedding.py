"""Embedding provider — local (HuggingFace) or OpenAI, powered by llama-index."""

from typing import Optional

from llama_index.core.embeddings import BaseEmbedding

from app.core.config import settings

_embed_model: Optional[BaseEmbedding] = None


class EmbeddingProvider:
    """Unified embedding interface backed by llama-index."""

    def __init__(self):
        self._dim: Optional[int] = None
        self._ready = False

    async def ensure_ready(self):
        """Lazy init the embedding backend."""
        if self._ready:
            return
        await self._init_model()
        self._ready = True

    async def _init_model(self):
        global _embed_model
        if _embed_model is not None:
            self._dim = len(_embed_model.get_text_embedding("test"))
            return

        import asyncio
        loop = asyncio.get_event_loop()

        if settings.local_embedding:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            print(f"Loading local embedding model via llama-index: {settings.local_embedding_model} ...")
            _embed_model = await loop.run_in_executor(
                None,
                lambda: HuggingFaceEmbedding(model_name=settings.local_embedding_model),
            )
        else:
            from llama_index.embeddings.openai import OpenAIEmbedding
            print(f"Using OpenAI embedding: {settings.embedding_model}")
            _embed_model = OpenAIEmbedding(
                model=settings.embedding_model,
                api_key=settings.embedding_api_key or settings.openai_api_key,
                api_base=settings.embedding_base_url,
            )

        test_emb = await loop.run_in_executor(None, _embed_model.get_text_embedding, "test")
        self._dim = len(test_emb)
        print(f"  -> dim={self._dim}")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of vectors."""
        await self.ensure_ready()
        if _embed_model is None:
            raise RuntimeError("Embedding model not initialized")
        return await _embed_model.aget_text_embedding_batch(texts)

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text. Returns one vector."""
        await self.ensure_ready()
        if _embed_model is None:
            raise RuntimeError("Embedding model not initialized")
        return await _embed_model.aget_text_embedding(text)

    @property
    def dim(self) -> int:
        if self._dim is None:
            return settings.embedding_dim
        return self._dim


embedding_provider = EmbeddingProvider()
