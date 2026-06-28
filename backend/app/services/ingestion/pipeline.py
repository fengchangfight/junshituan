"""Knowledge ingestion pipeline using LlamaIndex + Milvus."""

import asyncio
from typing import Optional
from functools import lru_cache

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.ingestion.milvus_store import milvus_store


class IngestionPipeline:
    """Ingests documents into an advisor's knowledge base."""

    def __init__(self):
        self._embed_client = None

    @property
    def embed_client(self):
        if self._embed_client is None:
            self._embed_client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        return self._embed_client

    async def ingest_text(
        self,
        persona_id: str,
        texts: list[str],
        sources: list[str],
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> int:
        """Ingest raw texts into Milvus vector store.

        Returns the total number of chunks embedded and stored.
        """
        # Step 1: Chunk all texts
        all_chunks = []
        for text, source in zip(texts, sources):
            chunks = self._chunk_text(text, chunk_size, chunk_overlap)
            for c in chunks:
                all_chunks.append({"text": c, "source": source})

        if not all_chunks:
            return 0

        # Step 2: Batch embed
        chunk_texts = [c["text"] for c in all_chunks]
        embeddings = await self._batch_embed(chunk_texts)

        # Step 3: Attach embeddings and insert
        for i, emb in enumerate(embeddings):
            all_chunks[i]["embedding"] = emb

        # Step 4: Ensure collection exists
        milvus_store.delete_collection(persona_id)
        milvus_store.create_collection(persona_id)

        # Step 5: Insert
        milvus_store.insert(persona_id, all_chunks)

        return len(all_chunks)

    async def search(
        self,
        persona_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Retrieve relevant knowledge chunks."""
        embedding = await self._embed_single(query)
        if not embedding:
            return []
        return milvus_store.search(persona_id, embedding, top_k=top_k)

    async def _batch_embed(self, texts: list[str], batch_size: int = 20) -> list[list[float]]:
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = await self.embed_client.embeddings.create(
                model=settings.embedding_model,
                input=batch,
            )
            for item in resp.data:
                embeddings.append(item.embedding)
        return embeddings

    async def _embed_single(self, text: str) -> Optional[list[float]]:
        try:
            resp = await self.embed_client.embeddings.create(
                model=settings.embedding_model,
                input=[text],
            )
            return resp.data[0].embedding
        except Exception:
            return None

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> list[str]:
        """Simple sliding-window chunker. Replace with llama-index SentenceSplitter for production."""
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            # Try to break at paragraph or sentence boundary
            if end < len(text):
                for sep in ["\n\n", "\n", "。", ". ", "；", "；"]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + chunk_size // 2:
                        end = last_sep + len(sep)
                        break
            chunks.append(text[start:end].strip())
            start = end - chunk_overlap
            if start >= len(text):
                break
        return [c for c in chunks if c]

    @staticmethod
    def get_llama_index_loader(content_type: str):
        """Get appropriate LlamaIndex document reader."""
        if content_type == "application/pdf":
            from llama_index.readers.file import PDFReader
            return PDFReader()
        else:
            # Default: plain text - use SimpleDirectoryReader or raw text
            return None


pipeline = IngestionPipeline()
