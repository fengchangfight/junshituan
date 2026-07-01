"""Milvus vector store — single collection with persona_id field.

All advisors share one collection `junshituan_knowledge`, filtered by persona_id.
"""

import re
from typing import Optional

from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker, DataType

try:
    from pymilvus.model.sparse import BM25EmbeddingFunction
    from pymilvus.model.sparse.bm25.tokenizers import build_default_analyzer
except ImportError:
    BM25EmbeddingFunction = None
    build_default_analyzer = None

from app.core.config import settings

COLLECTION_NAME = "junshituan_knowledge"


class MilvusStore:
    """Single-collection Milvus store with dense + BM25 sparse vectors.

    Schema:
      - id: VARCHAR (primary)
      - persona_id: VARCHAR
      - text: VARCHAR
      - embedding: FLOAT_VECTOR (dense)
      - sparse_vec: SPARSE_FLOAT_VECTOR (BM25)
      - source: VARCHAR
      - ref_doc_id: VARCHAR
    """

    def __init__(self):
        self._client: Optional[MilvusClient] = None
        self._initialized = False
        self._bm25_ef: Optional[BM25EmbeddingFunction] = None
        self._loaded = False

    def _lazy_init(self):
        if self._initialized:
            return
        self._client = MilvusClient(
            uri=f"http://{settings.milvus_host}:{settings.milvus_port}"
        )
        self._bm25_ef = BM25EmbeddingFunction(
            analyzer=build_default_analyzer(language="zh")
        )
        self._initialized = True

    @property
    def client(self) -> MilvusClient:
        self._lazy_init()
        return self._client

    # ── BM25 helpers ──────────────────────────────────────────────────

    def fit_bm25(self, corpus: list[str]):
        if self._bm25_ef:
            self._bm25_ef.fit(corpus)

    def encode_sparse(self, texts: list[str]) -> list[dict]:
        if self._bm25_ef:
            result = self._bm25_ef.encode_documents(texts)
            rows = []
            for i in range(result.shape[0]):
                row = result[i].tocoo()
                sparse = {int(idx): float(val) for idx, val in zip(row.col, row.data)}
                rows.append(sparse)
            return rows
        return [{} for _ in texts]

    def encode_query_sparse(self, queries: list[str]) -> list[dict]:
        if self._bm25_ef:
            result = self._bm25_ef.encode_queries(queries)
            rows = []
            for i in range(result.shape[0]):
                row = result[i].tocoo()
                rows.append({int(idx): float(val) for idx, val in zip(row.col, row.data)})
            return rows
        return [{} for _ in queries]

    # ── Collection management ──────────────────────────────────────────

    def ensure_collection(self, dim: int = None):
        """Create the single shared collection if it doesn't exist."""
        self._lazy_init()
        d = dim or settings.embedding_dim
        if self.client.has_collection(COLLECTION_NAME):
            return
        try:
            schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=256)
            schema.add_field(field_name="persona_id", datatype=DataType.VARCHAR, max_length=128)
            schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
            schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=d)
            schema.add_field(field_name="sparse_vec", datatype=DataType.SPARSE_FLOAT_VECTOR)
            schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=256)
            schema.add_field(field_name="ref_doc_id", datatype=DataType.VARCHAR, max_length=128)

            self.client.create_collection(collection_name=COLLECTION_NAME, schema=schema)

            index_params = self.client.prepare_index_params()
            index_params.add_index(field_name="embedding", index_type="FLAT", metric_type="COSINE")
            index_params.add_index(field_name="sparse_vec", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
            self.client.create_index(collection_name=COLLECTION_NAME, index_params=index_params)
            self._ensure_loaded()
            print(f"[Milvus] created collection: {COLLECTION_NAME}")
        except Exception as e:
            print(f"[Milvus] create_collection error: {e}")

    def _ensure_loaded(self):
        if self._loaded:
            return
        try:
            if self.client.has_collection(COLLECTION_NAME):
                self.client.load_collection(collection_name=COLLECTION_NAME)
                self._loaded = True
        except Exception:
            pass

    # ── Insert ────────────────────────────────────────────────────────

    def insert_batch(self, persona_id: str, chunks: list[dict], start_idx: int = 0) -> bool:
        self._lazy_init()
        try:
            data = []
            for i, chunk in enumerate(chunks):
                node_id = chunk.get("id") or f"{persona_id}_{start_idx + i}"
                entry = {
                    "id": str(node_id),
                    "persona_id": persona_id,
                    "text": chunk["text"],
                    "embedding": chunk["embedding"],
                    "source": chunk.get("source", ""),
                    "ref_doc_id": chunk.get("ref_doc_id", ""),
                }
                if "sparse_vec" in chunk:
                    entry["sparse_vec"] = chunk["sparse_vec"]
                else:
                    entry["sparse_vec"] = {}
                data.append(entry)
            self.client.insert(collection_name=COLLECTION_NAME, data=data)
            return True
        except Exception as e:
            import traceback
            print(f"[Milvus] insert_batch error for {persona_id}: {e}")
            traceback.print_exc()
            raise

    # ── Delete ────────────────────────────────────────────────────────

    def delete_by_ref_doc(self, persona_id: str, ref_doc_id: str) -> int:
        self._lazy_init()
        try:
            expr = f'persona_id == "{persona_id}" && ref_doc_id == "{ref_doc_id}"'
            result = self.client.delete(collection_name=COLLECTION_NAME, filter=expr)
            return result.get("delete_count", 0) if isinstance(result, dict) else 0
        except Exception as e:
            print(f"[Milvus] delete_by_ref_doc error: {e}")
            return 0

    def delete_persona(self, persona_id: str) -> int:
        """Delete all nodes for a persona (used when re-ingesting from scratch)."""
        self._lazy_init()
        try:
            expr = f'persona_id == "{persona_id}"'
            result = self.client.delete(collection_name=COLLECTION_NAME, filter=expr)
            return result.get("delete_count", 0) if isinstance(result, dict) else 0
        except Exception as e:
            print(f"[Milvus] delete_persona error: {e}")
            return 0

    # ── Search ────────────────────────────────────────────────────────

    def search(
        self,
        persona_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        query_sparse_vec: Optional[dict] = None,
    ) -> list[dict]:
        self._lazy_init()
        try:
            if not self.client.has_collection(COLLECTION_NAME):
                return []
            self._ensure_loaded()
            if query_sparse_vec:
                return self._hybrid_search(persona_id, query_embedding, query_sparse_vec, top_k)
            else:
                return self._dense_search(persona_id, query_embedding, top_k)
        except Exception as e:
            print(f"[Milvus] search error for {persona_id}: {e}")
            return []

    def _persona_filter(self, persona_id: str) -> str:
        return f'persona_id == "{persona_id}"'

    def _dense_search(self, persona_id: str, query_embedding: list[float], top_k: int) -> list[dict]:
        results = self.client.search(
            collection_name=COLLECTION_NAME,
            data=[query_embedding],
            anns_field="embedding",
            limit=top_k,
            filter=self._persona_filter(persona_id),
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
        persona_id: str,
        query_embedding: list[float],
        query_sparse_vec: dict,
        top_k: int,
    ) -> list[dict]:
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
        results = self.client.hybrid_search(
            collection_name=COLLECTION_NAME,
            reqs=[dense_req, sparse_req],
            rerank=ranker,
            limit=top_k,
            filter=self._persona_filter(persona_id),
            output_fields=["text", "source"],
        )
        if not results or not results[0]:
            return []
        return [
            {"text": r.get("entity", {}).get("text", ""),
             "source": r.get("entity", {}).get("source", ""),
             "score": r.get("distance", 0),
             "rank_type": "hybrid"}
            for r in results[0]
        ]

    # ── Stats ─────────────────────────────────────────────────────────

    def doc_count(self, persona_id: str) -> int:
        self._lazy_init()
        try:
            result = self.client.query(
                collection_name=COLLECTION_NAME,
                filter=self._persona_filter(persona_id),
                output_fields=["count(*)"],
            )
            return result[0].get("count(*)", 0) if result else 0
        except Exception:
            return 0


milvus_store = MilvusStore()
