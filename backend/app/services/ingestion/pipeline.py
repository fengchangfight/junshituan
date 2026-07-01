"""Knowledge ingestion pipeline — powered by llama-index (chunking + embedding) + custom Milvus hybrid search."""

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import Document as LlamaDocument

from app.core.embedding import embedding_provider
from app.services.ingestion.milvus_store import milvus_store

BATCH_SIZE = 32
MAX_CHUNKS_PER_INGEST = 10000


class IngestionPipeline:
    """Two-pass ingestion: fit BM25 on full corpus, then embed + insert in batches."""

    async def ingest_text(
        self,
        persona_id: str,
        texts: list[str],
        sources: list[str],
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> int:
        total_bytes = sum(len(t) for t in texts)
        print(f"[Ingest] persona={persona_id}, docs={len(texts)}, corpus_bytes={total_bytes}")

        # ── Pass 0: Chunk with llama-index SentenceSplitter ─────────────
        splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        all_nodes = []
        for text, source in zip(texts, sources):
            doc = LlamaDocument(text=text, metadata={"source": source})
            nodes = splitter.get_nodes_from_documents([doc])
            all_nodes.extend(nodes)
            if len(all_nodes) > MAX_CHUNKS_PER_INGEST:
                raise ValueError(
                    f"Too many chunks ({len(all_nodes)}). "
                    f"Reduce document size or split into multiple ingests."
                )

        if not all_nodes:
            return 0

        print(f"[Ingest] {len(all_nodes)} chunks, total_chars={sum(len(n.text) for n in all_nodes)}")

        dim = await self._get_dim()
        print(f"[Ingest] dim={dim}, creating collection...")
        milvus_store.delete_collection(persona_id)
        milvus_store.create_collection(persona_id, dim=dim)

        # ── Pass 1: Fit BM25 on all chunk texts ─────────────────────────
        chunk_texts = [n.text for n in all_nodes]
        print(f"[Ingest] fitting BM25 on {len(chunk_texts)} texts...")
        milvus_store.fit_bm25(chunk_texts)
        del chunk_texts

        # ── Pass 2: Embed + insert in batches ───────────────────────────
        total = 0
        for i in range(0, len(all_nodes), BATCH_SIZE):
            batch_nodes = all_nodes[i : i + BATCH_SIZE]
            batch_texts = [n.text for n in batch_nodes]

            embeddings = await embedding_provider.embed(batch_texts)
            sparse_vecs = milvus_store.encode_sparse(batch_texts)

            insert_data = []
            for j, node in enumerate(batch_nodes):
                entry = {
                    "text": node.text,
                    "source": node.metadata.get("source", ""),
                    "embedding": embeddings[j],
                }
                if j < len(sparse_vecs):
                    entry["sparse_vec"] = sparse_vecs[j]
                insert_data.append(entry)

            milvus_store.insert_batch(persona_id, insert_data, start_idx=total)
            total += len(batch_nodes)
            print(f"[Ingest] batch: {len(batch_nodes)} chunks inserted (total={total})")

        print(f"[Ingest] done: {total} chunks total")
        return total

    async def search(self, persona_id: str, query: str, top_k: int = 5) -> list[dict]:
        embedding = await embedding_provider.embed_single(query)
        if not embedding:
            return []
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


pipeline = IngestionPipeline()
