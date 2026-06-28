"""Knowledge ingestion pipeline using LlamaIndex + Milvus.

Embedding backend is auto-selected:
- LOCAL_EMBEDDING=true  → sentence-transformers (BGE, free, 512 dim)
- LOCAL_EMBEDDING=false → OpenAI text-embedding-3-small (API, 1536 dim)
"""

from typing import Optional

from app.core.config import settings
from app.core.embedding import embedding_provider
from app.services.ingestion.milvus_store import milvus_store


class IngestionPipeline:
    """Ingests documents into an advisor's knowledge base."""

    async def ingest_text(
        self,
        persona_id: str,
        texts: list[str],
        sources: list[str],
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> int:
        """Ingest raw texts into Milvus vector store."""
        all_chunks = []
        for text, source in zip(texts, sources):
            chunks = self._chunk_text(text, chunk_size, chunk_overlap)
            for c in chunks:
                all_chunks.append({"text": c, "source": source})

        if not all_chunks:
            return 0

        chunk_texts = [c["text"] for c in all_chunks]
        embeddings = await embedding_provider.embed(chunk_texts)

        for i, emb in enumerate(embeddings):
            all_chunks[i]["embedding"] = emb

        milvus_store.delete_collection(persona_id)
        dim = await self._get_dim()
        milvus_store.create_collection(persona_id, dim=dim)
        milvus_store.insert(persona_id, all_chunks)

        return len(all_chunks)

    async def search(
        self,
        persona_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Retrieve relevant knowledge chunks."""
        embedding = await embedding_provider.embed_single(query)
        if not embedding:
            return []
        return milvus_store.search(persona_id, embedding, top_k=top_k)

    async def _get_dim(self) -> int:
        await embedding_provider.ensure_ready()
        return embedding_provider.dim

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                for sep in ["\n\n", "\n", "。", ". ", "；"]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + chunk_size // 2:
                        end = last_sep + len(sep)
                        break
            chunks.append(text[start:end].strip())
            start = end - chunk_overlap
            if start >= len(text):
                break
        return [c for c in chunks if c]


pipeline = IngestionPipeline()
