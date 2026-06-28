"""Knowledge ingestion script for the Junshituan advisory council.

This script helps you ingest a historical figure's writings into the RAG system.
Place text files in data/corpus/<persona_id>/ and run this script to index them.

Usage:
    python scripts/ingest.py                    # ingest all
    python scripts/ingest.py --persona zhuge-liang  # ingest one
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import settings


def chunk_text(text: str, max_chars: int = 1000, overlap: int = 100) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        start += max_chars - overlap
    return chunks


def ingest_persona(persona_id: str, corpus_dir: Path, client, ef):
    persona_dir = corpus_dir / persona_id
    if not persona_dir.is_dir():
        print(f"  Skipping {persona_id}: no corpus directory")
        return

    txt_files = list(persona_dir.glob("*.txt"))
    if not txt_files:
        print(f"  Skipping {persona_id}: no .txt files found")
        return

    try:
        client.delete_collection(name=persona_id)
        print(f"  Deleted existing collection for {persona_id}")
    except Exception:
        pass

    collection = client.create_collection(name=persona_id, embedding_function=ef)
    print(f"  Created collection for {persona_id}")

    docs = []
    metas = []
    ids = []

    for f in txt_files:
        with open(f, "r", encoding="utf-8") as fp:
            text = fp.read()
        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            docs.append(chunk)
            metas.append({"source": f.name, "chunk": i})
            ids.append(f"{persona_id}_{f.stem}_{i}")
        print(f"    {f.name}: {len(chunks)} chunks")

    if docs:
        collection.add(documents=docs, metadatas=metas, ids=ids)
        print(f"  Indexed {len(docs)} chunks for {persona_id}")
    else:
        print(f"  No content to index for {persona_id}")


def main():
    parser = argparse.ArgumentParser(description="Ingest corpus into RAG vector store")
    parser.add_argument("--persona", type=str, help="Specific persona ID to ingest")
    args = parser.parse_args()

    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=settings.openai_api_key,
        api_base=settings.openai_base_url,
        model_name=settings.embedding_model,
    )

    corpus_dir = Path(settings.corpus_dir)

    if args.persona:
        print(f"Ingesting {args.persona}...")
        ingest_persona(args.persona, corpus_dir, client, ef)
    else:
        for d in corpus_dir.iterdir():
            if d.is_dir():
                print(f"Ingesting {d.name}...")
                ingest_persona(d.name, corpus_dir, client, ef)

    print("Done!")


if __name__ == "__main__":
    main()
