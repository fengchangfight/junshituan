"""Milvus vector store — hybrid search (dense + BM25 sparse).

Uses MilvusClient exclusively (no ORM-style Collection / connections API).
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


class MilvusStore:
    """Manages Milvus collections with dense + BM25 sparse vectors.

    Collection schema (per persona):
      - id: VARCHAR (primary)
      - text: VARCHAR
      - embedding: FLOAT_VECTOR (dense, BGE 512d or OpenAI 1536d)
      - sparse_vec: SPARSE_FLOAT_VECTOR (BM25)
      - source: VARCHAR
      - ref_doc_id: VARCHAR (for document-level dedup/deletion)
    """

    def __init__(self):
        self._client = None
        self._initialized = False
        self._bm25_ef: Optional[BM25EmbeddingFunction] = None
        self._loaded_collections: set[str] = set()

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

    def collection_name(self, persona_id: str) -> str:
        safe_id = re.sub(r"[^a-zA-Z0-9_]", "_", persona_id)
        return f"{settings.milvus_collection_prefix}{safe_id}"

    def create_collection(self, persona_id: str, dim: int = None) -> bool:
        self._lazy_init()
        name = self.collection_name(persona_id)
        d = dim or settings.embedding_dim
        try:
            schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=256)
            schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
            schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=d)
            schema.add_field(field_name="sparse_vec", datatype=DataType.SPARSE_FLOAT_VECTOR)
            schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=256)
            schema.add_field(field_name="ref_doc_id", datatype=DataType.VARCHAR, max_length=128)

            self.client.create_collection(collection_name=name, schema=schema)

            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                index_type="FLAT",
                metric_type="COSINE",
            )
            index_params.add_index(
                field_name="sparse_vec",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
            )
            self.client.create_index(collection_name=name, index_params=index_params)
            self.client.load_collection(collection_name=name)
            self._loaded_collections.add(name)
            return True
        except Exception as e:
            print(f"Milvus create_collection error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def insert(self, persona_id: str, chunks: list[dict]) -> bool:
        return self.insert_batch(persona_id, chunks, start_idx=0)

    def insert_batch(self, persona_id: str, chunks: list[dict], start_idx: int = 0) -> bool:
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            data = []
            for i, chunk in enumerate(chunks):
                node_id = chunk.get("id") or f"{persona_id}_{start_idx + i}"
                entry = {
                    "id": str(node_id),
                    "text": chunk["text"],
                    "embedding": chunk["embedding"],
                    "source": chunk.get("source", ""),
                    "ref_doc_id": chunk.get("ref_doc_id", ""),
                }
                if "sparse_vec" in chunk:
                    entry["sparse_vec"] = chunk["sparse_vec"]
                data.append(entry)
            self.client.insert(collection_name=name, data=data)
            return True
        except Exception as e:
            import traceback
            print(f"Milvus insert_batch error: {e}")
            traceback.print_exc()
            raise

    def delete_by_ref_doc(self, persona_id: str, ref_doc_id: str) -> int:
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            expr = f'ref_doc_id == "{ref_doc_id}"'
            result = self.client.delete(collection_name=name, filter=expr)
            return result.get("delete_count", 0) if isinstance(result, dict) else 0
        except Exception as e:
            print(f"Milvus delete_by_ref_doc error: {e}")
            return 0

    def ensure_collection(self, persona_id: str, dim: int = None):
        name = self.collection_name(persona_id)
        try:
            if self.client.has_collection(name):
                return
        except Exception:
            pass
        self.create_collection(persona_id, dim=dim)

    # ── Hybrid search ──────────────────────────────────────────────────

    def search(
        self,
        persona_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        query_sparse_vec: Optional[dict] = None,
    ) -> list[dict]:
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            self._ensure_loaded(name)
            if query_sparse_vec:
                return self._hybrid_search(name, query_embedding, query_sparse_vec, top_k)
            else:
                return self._dense_search(name, query_embedding, top_k)
        except Exception as e:
            print(f"Milvus search error: {e}")
            return []

    def _ensure_loaded(self, name: str):
        if name not in self._loaded_collections:
            try:
                self.client.load_collection(collection_name=name)
                self._loaded_collections.add(name)
            except Exception:
                pass

    def _dense_search(self, name: str, query_embedding: list[float], top_k: int) -> list[dict]:
        results = self.client.search(
            collection_name=name,
            data=[query_embedding],
            anns_field="embedding",
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
            collection_name=name,
            reqs=[dense_req, sparse_req],
            rerank=ranker,
            limit=top_k,
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

    # ── Maintenance ────────────────────────────────────────────────────

    def delete_collection(self, persona_id: str):
        self._lazy_init()
        name = self.collection_name(persona_id)
        self._loaded_collections.discard(name)
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
