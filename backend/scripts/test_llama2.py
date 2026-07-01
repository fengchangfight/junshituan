import sys, asyncio, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def main():
    from app.core.embedding import embedding_provider
    await embedding_provider.ensure_ready()
    print('dim:', embedding_provider.dim)

    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core import Document
    s = SentenceSplitter(chunk_size=200, chunk_overlap=20)
    nodes = s.get_nodes_from_documents([Document(text='test text here.')])
    print('chunks:', len(nodes))

    from app.services.ingestion.milvus_hybrid_vs import MilvusHybridVectorStore
    vs = MilvusHybridVectorStore(persona_id='test-quick', dim=512)
    print('vs type:', type(vs).__name__)

    from app.services.ingestion.pipeline import _LlamaEmbedAdapter
    adapter = _LlamaEmbedAdapter(embedding_provider)
    result = adapter(nodes)
    print('adapter result:', len(result), 'has embedding:', result[0].embedding is not None)

asyncio.run(main())
