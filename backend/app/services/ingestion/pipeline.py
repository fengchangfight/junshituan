"""Knowledge ingestion pipeline — powered by llama-index IngestionPipeline.

- Chunking: SentenceSplitter
- Embedding: via EmbeddingProvider (HuggingFace / OpenAI)
- Dedup: DocstoreStrategy.UPSERTS_AND_DELETE (skip unchanged docs, delete old nodes on change)
- BM25: pre-fitted on full corpus before pipeline runs
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

from llama_index.core import Document as LlamaDocument
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TransformComponent
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.ingestion import DocstoreStrategy

from app.core.config import settings
from app.core.embedding import embedding_provider
from app.services.ingestion.milvus_store import milvus_store
from app.services.ingestion.milvus_hybrid_vs import MilvusHybridVectorStore

BATCH_SIZE = 32
MAX_CHUNKS_PER_INGEST = 10000


class IngestionPipelineService:
    """Manages the full ingest lifecycle: fit BM25, run llama-index pipeline."""

    def _docstore_path(self, persona_id: str) -> str:
        dir_path = os.path.join("data", "docstore")
        os.makedirs(dir_path, exist_ok=True)
        return os.path.join(dir_path, f"{persona_id}.json")

    def _load_docstore(self, persona_id: str) -> SimpleDocumentStore:
        path = self._docstore_path(persona_id)
        if os.path.exists(path):
            return SimpleDocumentStore.from_persist_path(path)
        return SimpleDocumentStore()

    def _save_docstore(self, persona_id: str, docstore: SimpleDocumentStore):
        docstore.persist(self._docstore_path(persona_id))

    async def ingest_text(
        self,
        persona_id: str,
        texts: list[str],
        sources: list[str],
        doc_hashes: Optional[list[str]] = None,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> int:
        """Ingest documents with llama-index dedup.

        Args:
            doc_hashes: Content hashes per document (e.g., sha256 of title+content).
                        Used as llama-index doc_id for stable identity across re-ingests.
        """
        total_bytes = sum(len(t) for t in texts)
        print(f"[Ingest] persona={persona_id}, docs={len(texts)}, corpus_bytes={total_bytes}")

        # ── If docstore is empty, start fresh (delete old nodes) ─────────
        docstore = self._load_docstore(persona_id)
        if len(docstore.docs) == 0:
            print("[Ingest] docstore empty, deleting old nodes for clean start")
            milvus_store.delete_persona(persona_id)

        # ── Ensure collection exists ────────────────────────────────────
        dim = await self._get_dim()
        milvus_store.ensure_collection(dim=dim)

        # ── Fit BM25 on full corpus ─────────────────────────────────────
        # Use ONE splitter instance so BM25 and pipeline chunks are identical
        splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        all_chunk_texts = []
        for text in texts:
            for node in splitter.get_nodes_from_documents([LlamaDocument(text=text)]):
                all_chunk_texts.append(node.get_content())
                if len(all_chunk_texts) > MAX_CHUNKS_PER_INGEST:
                    raise ValueError(f"Too many chunks ({len(all_chunk_texts)}).")

        if not all_chunk_texts:
            return 0

        print(f"[Ingest] {len(all_chunk_texts)} chunks total, fitting BM25...")
        milvus_store.fit_bm25(all_chunk_texts)
        del all_chunk_texts

        # ── Build llama-index Documents ─────────────────────────────────
        llama_docs = []
        for i, (text, source) in enumerate(zip(texts, sources)):
            doc_id = doc_hashes[i] if doc_hashes and i < len(doc_hashes) else None
            metadata = {"source": source, "file_name": source}
            if doc_id:
                metadata["ref_doc_id"] = doc_id
                metadata["content_hash"] = doc_id
            llama_docs.append(
                LlamaDocument(text=text, metadata=metadata, doc_id=doc_id)
            )

        # ── Run llama-index IngestionPipeline ───────────────────────────
        vector_store = MilvusHybridVectorStore(persona_id=persona_id, dim=dim)
        docstore = self._load_docstore(persona_id)

        pipeline = IngestionPipeline(
            transformations=[
                splitter,  # Reuse SAME splitter instance
                _LlamaEmbedAdapter(embedding_provider),
            ],
            vector_store=vector_store,
            docstore=docstore,
            docstore_strategy=DocstoreStrategy.UPSERTS_AND_DELETE,
        )

        print(f"[Ingest] running llama-index pipeline (UPSERTS_AND_DELETE)...")
        nodes = await asyncio.get_event_loop().run_in_executor(
            None, lambda: pipeline.run(documents=llama_docs)
        )

        self._save_docstore(persona_id, docstore)
        print(f"[Ingest] done: {len(nodes)} nodes total (new or updated)")
        return len(nodes)

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


class _LlamaEmbedAdapter(TransformComponent):
    """Bridge EmbeddingProvider into llama-index TransformComponent.

    EmbeddingProvider is async; llama-index transformations are sync.
    We run the embedding in a fresh event loop inside each __call__.
    """

    def __init__(self, provider, **kwargs):
        super().__init__(**kwargs)
        self._provider = provider

    def __call__(self, nodes, **kwargs):
        texts = [node.get_content() for node in nodes]
        if not texts:
            return nodes

        embeddings = self._provider.embed_sync(texts)
        for node, emb in zip(nodes, embeddings):
            node.embedding = emb
        return nodes


pipeline = IngestionPipelineService()
