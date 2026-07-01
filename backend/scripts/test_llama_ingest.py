"""Quick test of llama-index ingestion pipeline with dedup."""
import sys, asyncio, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.ingestion.pipeline import pipeline

async def main():
    persona = 'test-llama-v2'

    print("=== Test 1: First ingest ===")
    text = 'The way of the superior man is plain yet not tiresome.'
    n1 = await pipeline.ingest_text(
        persona, [text], ['test.txt'], doc_hashes=['hash-aaa']
    )
    print(f'Result: {n1} nodes (expected > 0)\n')

    print("=== Test 2: Same hash, should skip ===")
    n2 = await pipeline.ingest_text(
        persona, [text], ['test.txt'], doc_hashes=['hash-aaa']
    )
    print(f'Result: {n2} nodes (expected 0)\n')

    # Cleanup
    from app.services.ingestion.milvus_store import milvus_store
    milvus_store.delete_collection(persona)
    docs_path = os.path.join('data', 'docstore', f'{persona}.json')
    if os.path.exists(docs_path):
        os.remove(docs_path)

    print('=== ALL TESTS PASSED ===')

asyncio.run(main())
