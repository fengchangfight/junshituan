"""Knowledge ingestion pipeline — hybrid search (dense + BM25).

Embedding backend:
- LOCAL_EMBEDDING=true  → sentence-transformers (BGE, 512 dim)
- LOCAL_EMBEDDING=false → OpenAI text-embedding-3-small (1536 dim)

BM25 sparse vectors are always generated alongside dense embeddings.
"""

import asyncio
from typing import Optional

from app.core.config import settings
from app.core.embedding import embedding_provider
from app.services.ingestion.milvus_store import milvus_store


class IngestionPipeline:

    async def ingest_text(
        self,
        persona_id: str,
        texts: list[str],
        sources: list[str],
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> int:
        """Ingest raw texts into Milvus with dense + BM25 sparse vectors."""
        all_chunks = []
        for text, source in zip(texts, sources):
            chunks = self._chunk_text(text, chunk_size, chunk_overlap)
            for c in chunks:
                all_chunks.append({"text": c, "source": source})

        if not all_chunks:
            return 0

        chunk_texts = [c["text"] for c in all_chunks]

        # Dense embeddings
        embeddings = await embedding_provider.embed(chunk_texts)

        # BM25 sparse vectors — fit on all chunk texts, then encode
        milvus_store.fit_bm25(chunk_texts)
        sparse_vecs = milvus_store.encode_sparse(chunk_texts)

        for i in range(len(all_chunks)):
            all_chunks[i]["embedding"] = embeddings[i]
            if i < len(sparse_vecs):
                all_chunks[i]["sparse_vec"] = sparse_vecs[i]

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
        """Hybrid search: dense + BM25. Falls back to pure dense if sparse unavailable."""
        embedding = await embedding_provider.embed_single(query)
        if not embedding:
            return []

        # Try sparse BM25 encoding for hybrid search
        try:
            sparse_vecs = milvus_store.encode_query_sparse([query])
            sparse_vec = sparse_vecs[0] if sparse_vecs else None
        except Exception:
            sparse_vec = None

        return milvus_store.search(
            persona_id, embedding, top_k=top_k, query_sparse_vec=sparse_vec,
        )

    async def _get_dim(self) -> int:
        await embedding_provider.ensure_ready()
        return embedding_provider.dim

    def _chunk_text(self, text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[str]:
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
