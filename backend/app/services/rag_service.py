import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import settings


class RAGService:
    def __init__(self):
        self._initialized = False
        self._client = None
        self._ef = None

    def _lazy_init(self):
        if self._initialized:
            return
        try:
            self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
            self._ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=settings.openai_api_key,
                api_base=settings.openai_base_url,
                model_name=settings.embedding_model,
            )
        except Exception as e:
            print(f"RAG: init failed ({e}), RAG features disabled")
            self._client = None
            self._ef = None
        self._initialized = True

    def _ingest_dir(
        self,
        persona_id: str,
        directory: Path,
        collection,
    ):
        documents = []
        metadatas = []
        ids = []

        for f in directory.glob("*.txt"):
            with open(f, "r", encoding="utf-8") as fp:
                text = fp.read()
            chunks = self._chunk_text(text, max_chars=1000, overlap=100)
            for i, chunk in enumerate(chunks):
                documents.append(chunk)
                metadatas.append({"source": f.name, "chunk": i})
                ids.append(f"{persona_id}_{f.stem}_{i}")

        if documents:
            collection.add(documents=documents, metadatas=metadatas, ids=ids)

    def _chunk_text(self, text: str, max_chars: int = 1000, overlap: int = 100) -> list[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            chunks.append(text[start:end])
            start += max_chars - overlap
        return chunks

    def query(self, persona_id: str, query: str, n_results: int = 3) -> str:
        self._lazy_init()
        if not self._client:
            return ""
        try:
            collection = self._client.get_collection(
                name=persona_id, embedding_function=self._ef
            )
            results = collection.query(query_texts=[query], n_results=n_results)
            documents = results.get("documents", [[]])[0]
            if not documents:
                return ""
            return "\n\n---\n\n".join(documents)
        except Exception:
            return ""

    def query_multi(self, persona_ids: list[str], query: str) -> dict[str, str]:
        result = {}
        for pid in persona_ids:
            ctx = self.query(pid, query)
            if ctx:
                result[pid] = ctx
        return result


rag_service = RAGService()
