"""Milvus vector store wrapper for advisor knowledge bases."""

from typing import Optional

from app.core.config import settings


class MilvusStore:
    """Manages Milvus collections for each advisor's knowledge base."""

    def __init__(self):
        self._client = None
        self._initialized = False

    def _lazy_init(self):
        if self._initialized:
            return

        if settings.milvus_lite:
            from milvus_lite import MilvusClient as LiteClient
            import os
            db_path = settings.milvus_lite_db_path
            os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
            self._client = LiteClient(db_path)
        else:
            from pymilvus import connections
            connections.connect(
                alias="default",
                host=settings.milvus_host,
                port=settings.milvus_port,
            )
            from pymilvus import MilvusClient
            self._client = MilvusClient(
                uri=f"http://{settings.milvus_host}:{settings.milvus_port}"
            )
        self._initialized = True

    @property
    def client(self):
        self._lazy_init()
        return self._client

    def collection_name(self, persona_id: str) -> str:
        return f"{settings.milvus_collection_prefix}{persona_id}"

    def create_collection(self, persona_id: str, dim: int = None) -> bool:
        self._lazy_init()
        name = self.collection_name(persona_id)
        d = dim or settings.embedding_dim
        try:
            if settings.milvus_lite:
                self.client.create_collection(
                    collection_name=name,
                    dimension=d,
                    metric_type="COSINE",
                )
            else:
                from pymilvus import CollectionSchema, FieldSchema, DataType
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
                    FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=d),
                    FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=256),
                ]
                schema = CollectionSchema(fields, description=f"KB for {persona_id}")
                from pymilvus import Collection
                Collection(name=name, schema=schema)
            return True
        except Exception as e:
            print(f"Milvus create_collection error: {e}")
            return False

    def insert(self, persona_id: str, chunks: list[dict]) -> bool:
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            data = []
            for i, chunk in enumerate(chunks):
                data.append({
                    "id": f"{persona_id}_{i}",
                    "text": chunk["text"],
                    "embedding": chunk["embedding"],
                    "source": chunk.get("source", ""),
                })
            if settings.milvus_lite:
                self.client.insert(collection_name=name, data=data)
            else:
                self.client.insert(collection_name=name, data=data)
            return True
        except Exception as e:
            print(f"Milvus insert error: {e}")
            return False

    def search(
        self,
        persona_id: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            if settings.milvus_lite:
                results = self.client.search(
                    collection_name=name,
                    data=[query_embedding],
                    limit=top_k,
                    output_fields=["text", "source"],
                )
            else:
                results = self.client.search(
                    collection_name=name,
                    data=[query_embedding],
                    limit=top_k,
                    output_fields=["text", "source"],
                )
            if not results or not results[0]:
                return []
            return [
                {"text": hit.get("entity", {}).get("text", ""),
                 "source": hit.get("entity", {}).get("source", ""),
                 "score": hit.get("distance", 0)}
                for hit in results[0]
            ]
        except Exception as e:
            print(f"Milvus search error: {e}")
            return []

    def delete_collection(self, persona_id: str):
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            if settings.milvus_lite:
                self.client.drop_collection(name)
            else:
                self.client.drop_collection(name)
        except Exception:
            pass

    def doc_count(self, persona_id: str) -> int:
        self._lazy_init()
        name = self.collection_name(persona_id)
        try:
            if settings.milvus_lite:
                stats = self.client.get_collection_stats(name)
                return stats.get("row_count", 0)
            else:
                stats = self.client.get_collection_stats(name)
                return stats.get("row_count", 0)
        except Exception:
            return 0


milvus_store = MilvusStore()
