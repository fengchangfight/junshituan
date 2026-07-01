"""Knowledge ingestion CLI for the Junshituan advisory council.

Usage:
  python scripts/ingest.py                    # ingest all personas
  python scripts/ingest.py --persona zhuge-liang  # ingest one
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ingestion.pipeline import pipeline as ingest_pipeline
from app.core.embedding import embedding_provider


async def ingest_persona(persona_id: str, corpus_dir: Path):
    persona_dir = corpus_dir / persona_id
    if not persona_dir.is_dir():
        print(f"  Skipping {persona_id}: no corpus directory")
        return

    txt_files = list(persona_dir.glob("*.txt"))
    if not txt_files:
        print(f"  Skipping {persona_id}: no .txt files")
        return

    texts = []
    sources = []
    for f in txt_files:
        with open(f, "r", encoding="utf-8") as fp:
            text = fp.read()
        texts.append(text)
        sources.append(f.name)
        print(f"    {f.name}: {len(text)} chars")

    total = await ingest_pipeline.ingest_text(persona_id, texts, sources)
    print(f"  → {persona_id}: {total} chunks indexed (dim={await _get_dim()})")


async def _get_dim() -> int:
    await embedding_provider.ensure_ready()
    return embedding_provider.dim


async def main():
    parser = argparse.ArgumentParser(description="Ingest corpus into Milvus vector store")
    parser.add_argument("--persona", type=str, help="Specific persona ID to ingest")
    args = parser.parse_args()

    await embedding_provider.ensure_ready()
    backend = "local" if hasattr(embedding_provider, '_dim') and embedding_provider._dim else "OpenAI"
    print(f"Embedding backend: {backend} dim={embedding_provider.dim}")

    corpus_dir = Path("data/corpus")

    if args.persona:
        print(f"Ingesting {args.persona}...")
        await ingest_persona(args.persona, corpus_dir)
    else:
        for d in corpus_dir.iterdir():
            if d.is_dir():
                print(f"Ingesting {d.name}...")
                await ingest_persona(d.name, corpus_dir)

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
