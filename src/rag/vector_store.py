"""
Vector Store
向量存储层 — 基于 Milvus 的文档向量索引与检索
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime


class VectorStore:
    """Milvus向量存储，支持文档索引和增量更新"""

    def __init__(self, config: dict, milvus_manager, embedding_service):
        self.config = config
        self.milvus = milvus_manager
        self.embedding = embedding_service
        self.collection_name = config.get('collection', 'documents')
        self.top_k = config.get('top_k_vector', 10)
        self._initialized = False

    async def initialize(self):
        """初始化向量存储"""
        await self.milvus.get_or_create_collection(self.collection_name)
        self._initialized = True
        print(f"[VectorStore] Initialized, collection='{self.collection_name}'")

    async def index_document(self, doc_id: str, text: str, metadata: dict = None) -> int:
        """索引单个文档（分块后向量化存储）"""
        from ..llm.embeddings import EmbeddingService
        embed_svc = self.embedding

        chunks = embed_svc.chunk_text(
            text,
            chunk_size=self.config.get('chunk_size', 500),
            overlap=self.config.get('chunk_overlap', 50)
        )

        embeddings = await embed_svc.encode(chunks)

        vectors = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            vectors.append({
                'id': f"{doc_id}_chunk_{i}",
                'text': chunk,
                'embedding': emb,
                'metadata': {
                    **(metadata or {}),
                    'doc_id': doc_id,
                    'chunk_index': i,
                    'total_chunks': len(chunks)
                },
                'timestamp': datetime.now().timestamp()
            })

        await self.milvus.insert(self.collection_name, vectors)
        print(f"[VectorStore] Indexed doc '{doc_id}': {len(chunks)} chunks")
        return len(chunks)

    async def index_documents(self, docs: List[Dict[str, Any]]) -> int:
        """批量索引文档"""
        total = 0
        for doc in docs:
            total += await self.index_document(
                doc_id=doc['id'],
                text=doc.get('text', doc.get('content', '')),
                metadata=doc.get('metadata', {})
            )
        return total

    async def search(
        self,
        query: str,
        top_k: int = None,
        filter_expr: str = None
    ) -> List[Dict[str, Any]]:
        """向量检索"""
        top_k = top_k or self.top_k
        query_embedding = await self.embedding.encode_single(query)
        results = await self.milvus.search(
            self.collection_name,
            query_embedding,
            top_k=top_k,
            filter_expr=filter_expr
        )

        # 按doc_id去重，保留每篇文档最高分的chunk
        seen_docs = {}
        for r in results:
            doc_id = r.get('metadata', {}).get('doc_id', r['id'])
            if doc_id not in seen_docs or r['score'] > seen_docs[doc_id]['score']:
                seen_docs[doc_id] = r

        deduped = list(seen_docs.values())
        deduped.sort(key=lambda x: x['score'], reverse=True)
        return deduped

    async def delete_document(self, doc_id: str):
        """删除文档的所有向量"""
        ids = [f"{doc_id}_chunk_{i}" for i in range(10000)]
        await self.milvus.delete_by_ids(self.collection_name, ids)
        print(f"[VectorStore] Deleted document '{doc_id}'")

    async def incremental_update(self, doc_id: str, new_text: str, metadata: dict = None):
        """增量更新文档向量（先删后插）"""
        await self.delete_document(doc_id)
        await self.index_document(doc_id, new_text, metadata)
        print(f"[VectorStore] Incrementally updated document '{doc_id}'")

    async def get_collection_stats(self) -> dict:
        """获取集合统计信息"""
        return {
            'collection': self.collection_name,
            'initialized': self._initialized
        }
