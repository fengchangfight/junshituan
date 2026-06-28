"""Milvus vector store — hybrid search (dense + BM25 sparse).

Requires Milvus Standalone (Docker: `docker compose up -d milvus etcd minio`).
"""

from typing import Optional

from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType
from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker
from pymilvus.model.sparse import BM25EmbeddingFunction

from app.core.config import settings


class MilvusStore:
    """Manages Milvus collections with dense + BM25 sparse vectors.

    Collection schema (per persona):
      - id: VARCHAR (primary)
      - text: VARCHAR
      - embedding: FLOAT_VECTOR (dense, BGE 512d or OpenAI 1536d)
      - sparse_vec: SPARSE_FLOAT_VECTOR (BM25)
      - source: VARCHAR
    """

    def __init__(self):
        self._client = None
        self._initialized = False
        self._bm25_ef: Optional[BM25EmbeddingFunction] = None

    def _lazy_init(self):
        if self._initialized:
            return

        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=settings.milvus_port,
        )
        self._client = MilvusClient(
            uri=f"http://{settings.milvus_host}:{settings.milvus_port}"
        )
        self._bm25_ef = BM25EmbeddingFunction()
        self._initialized = True

    @property
    def client(self) -> MilvusClient:
        self._lazy_init()
        return self._client

    # ── BM25 helpers ──────────────────────────────────────────────────

    def fit_bm25(self, corpus: list[str]):
        """Fit BM25 on a corpus before encoding queries."""
        if self._bm25_ef:
            self._bm25_ef.fit(corpus)

    def encode_sparse(self, texts: list[str]) -> list[dict]:
        """Encode texts to sparse BM25 vectors for insertion."""
        if self._bm25_ef:
            return self._bm25_ef.encode_documents(texts)
        return [{} for _ in texts]

    def encode_query_sparse(self, queries: list[str]) -> list[dict]:
        """Encode queries to sparse BM25 vectors for search."""
        if self._bm25_ef:
            return self._bm25_ef.encode_queries(queries)
        return [{} for _ in queries]

    # ── Collection management ──────────────────────────────────────────

    def collection_name(self, persona_id: str) -> str:
        return f"{settings.milvus_collection_prefix}{persona_id}"

    def create_collection(self, persona_id: str, dim: int = None) -> bool:
        self._lazy_init()
        name = self.collection_name(persona_id)
        d = dim or settings.embedding_dim
        try:
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=d),
                FieldSchema(name="sparse_vec", dtype=DataType.SPARSE_FLOAT_VECTOR),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=256),
            ]
            schema = CollectionSchema(fields, description=f"KB for {persona_id}")
            Collection(name=name, schema=schema)
            return True
        except Exception as e:
            print(f"Milvus create_collection error: {e}")
            return False

    def insert(self, persona_id: str, chunks: list[dict]) -> bool:
        """Insert chunks with both dense and sparse vectors.

        Each chunk dict: {text, embedding, sparse_vec, source}
        """
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            data = []
            for i, chunk in enumerate(chunks):
                entry = {
                    "id": f"{persona_id}_{i}",
                    "text": chunk["text"],
                    "embedding": chunk["embedding"],
                    "source": chunk.get("source", ""),
                }
                if "sparse_vec" in chunk:
                    entry["sparse_vec"] = chunk["sparse_vec"]
                data.append(entry)
            self.client.insert(collection_name=name, data=data)
            return True
        except Exception as e:
            print(f"Milvus insert error: {e}")
            return False

    # ── Hybrid search ──────────────────────────────────────────────────

    def search(
        self,
        persona_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        query_sparse_vec: Optional[dict] = None,
    ) -> list[dict]:
        """Hybrid search: dense + BM25 sparse.

        If sparse_vec provided → WeightedRanker(0.6 dense, 0.4 BM25).
        Otherwise → pure dense cosine.
        """
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            if query_sparse_vec:
                return self._hybrid_search(name, query_embedding, query_sparse_vec, top_k)
            else:
                return self._dense_search(name, query_embedding, top_k)
        except Exception as e:
            print(f"Milvus search error: {e}")
            return []

    def _dense_search(self, name: str, query_embedding: list[float], top_k: int) -> list[dict]:
        results = self.client.search(
            collection_name=name,
            data=[query_embedding],
            limit=top_k,
            output_fields=["text", "source"],
            search_params={"metric_type": "COSINE"},
        )
        if not results or not results[0]:
            return []
        return [
            {"text": r.get("entity", {}).get("text", ""),
             "source": r.get("entity", {}).get("source", ""),
             "score": r.get("distance", 0),
             "rank_type": "dense"}
            for r in results[0]
        ]

    def _hybrid_search(
        self,
        name: str,
        query_embedding: list[float],
        query_sparse_vec: dict,
        top_k: int,
    ) -> list[dict]:
        """Weighted hybrid search via Milvus hybrid_search API."""
        col = Collection(name)
        col.load()

        dense_req = AnnSearchRequest(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE"},
            limit=top_k * 2,
        )
        sparse_req = AnnSearchRequest(
            data=[query_sparse_vec],
            anns_field="sparse_vec",
            param={"metric_type": "IP"},
            limit=top_k * 2,
        )

        ranker = WeightedRanker(0.6, 0.4)
        results = col.hybrid_search(
            reqs=[dense_req, sparse_req],
            rerank=ranker,
            limit=top_k,
            output_fields=["text", "source"],
        )

        if not results or not results[0]:
            return []
        return [
            {"text": r.entity.get("text", ""),
             "source": r.entity.get("source", ""),
             "score": r.distance,
             "rank_type": "hybrid"}
            for r in results[0]
        ]

    # ── Maintenance ────────────────────────────────────────────────────

    def delete_collection(self, persona_id: str):
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            self.client.drop_collection(name)
        except Exception:
            pass

    def doc_count(self, persona_id: str) -> int:
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            stats = self.client.get_collection_stats(name)
            return stats.get("row_count", 0)
        except Exception:
            return 0


milvus_store = MilvusStore()
