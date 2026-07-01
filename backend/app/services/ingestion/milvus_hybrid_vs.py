"""llama-index VectorStore adapter for our Milvus hybrid-search store."""

from typing import Any, List, Optional
from pydantic import Field, PrivateAttr

from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    VectorStoreQuery,
    VectorStoreQueryResult,
    MetadataFilters,
)
from llama_index.core.schema import BaseNode, TextNode

from app.services.ingestion.milvus_store import milvus_store


class MilvusHybridVectorStore(BasePydanticVectorStore):
    """VectorStore adapter wrapping our MilvusStore for llama-index.

    Handles both dense vectors (via llama-index embeddings) and sparse BM25 vectors
    (via pymilvus-model), enabling hybrid search while using llama-index's
    IngestionPipeline for chunking, dedup, and lifecycle management.
    """

    stores_text: bool = Field(default=True)
    is_embedding_query: bool = Field(default=True)
    persona_id: str = Field(default="")
    dim: int = Field(default=512)

    def __init__(self, persona_id: str, dim: int, **kwargs):
        super().__init__(persona_id=persona_id, dim=dim, **kwargs)

    @property
    def _store(self):
        return milvus_store

    @property
    def client(self):
        return milvus_store

    # ── llama-index VectorStore protocol ────────────────────────────────

    def add(self, nodes: List[BaseNode], **add_kwargs: Any) -> List[str]:
        """Add nodes with embeddings already populated by the ingestion pipeline."""
        if not nodes:
            return []

        # Filter out empty-content nodes (SentenceSplitter may produce empty chunks)
        nodes = [n for n in nodes if n.get_content().strip()]

        texts = [node.get_content() for node in nodes]
        sparse_vecs = self._store.encode_sparse(texts)

        batch = []
        for i, node in enumerate(nodes):
            ref_doc_id = node.ref_doc_id or node.metadata.get("ref_doc_id", "")
            entry = {
                "id": node.node_id,
                "text": node.get_content(),
                "source": node.metadata.get("source", node.metadata.get("file_name", "")),
                "embedding": node.embedding,
                "ref_doc_id": ref_doc_id or "",
            }
            if i < len(sparse_vecs):
                entry["sparse_vec"] = sparse_vecs[i]
            batch.append(entry)

        self._store.insert_batch(self.persona_id, batch, start_idx=0)
        return [n.node_id for n in nodes]

    def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
        """Delete all nodes belonging to a document."""
        self._store.delete_by_ref_doc(self.persona_id, ref_doc_id)

    def delete_nodes(
        self,
        node_ids: Optional[List[str]] = None,
        filters: Optional[MetadataFilters] = None,
        **delete_kwargs: Any,
    ) -> None:
        """Delete specific nodes by ID (not used by default DocstoreStrategy)."""
        if not node_ids:
            return
        name = self._store.collection_name(self.persona_id)
        ids_str = ", ".join(f'"{nid}"' for nid in node_ids)
        try:
            self._store.client.delete(collection_name=name, filter=f"id in [{ids_str}]")
        except Exception as e:
            print(f"MilvusHybridVS delete_nodes error: {e}")

    def query(self, query: VectorStoreQuery, **kwargs: Any) -> VectorStoreQueryResult:
        """Dense-only search (used by llama-index retrievers)."""
        if query.query_embedding is None:
            return VectorStoreQueryResult(nodes=[], similarities=[], ids=[])

        results = self._store._dense_search(
            self._store.collection_name(self.persona_id),
            query.query_embedding,
            top_k=query.similarity_top_k,
        )

        nodes = []
        similarities = []
        ids = []
        for r in results:
            node = TextNode(
                text=r.get("text", ""),
                metadata={"source": r.get("source", ""), "score": r.get("score", 0)},
            )
            nodes.append(node)
            similarities.append(r.get("score", 0))
            ids.append(r.get("id", ""))

        return VectorStoreQueryResult(nodes=nodes, similarities=similarities, ids=ids)

    def clear(self) -> None:
        """Drop the entire collection."""
        self._store.delete_collection(self.persona_id)
        self._store._loaded_collections.discard(
            self._store.collection_name(self.persona_id)
        )
