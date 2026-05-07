"""
RAG Service
RAG核心服务 — 整合文档加载、向量检索、图谱检索和融合排序
"""

import asyncio
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from .document_loader import DocumentLoader, Document
from .vector_store import VectorStore
from .kg_retriever import KnowledgeGraphRetriever
from .retrieval_fusion import RetrievalFusion, SearchResult


class RAGService:
    """双路混合RAG核心服务"""

    def __init__(self, config: dict, milvus_manager, neo4j_manager, embedding_service):
        self.config = config
        self.milvus = milvus_manager
        self.neo4j = neo4j_manager
        self.embedding = embedding_service

        self.loader = DocumentLoader(config.get('rag', {}))
        self.vector_store = VectorStore(
            config.get('rag', {}), milvus_manager, embedding_service
        )
        self.kg_retriever = KnowledgeGraphRetriever(
            config.get('rag', {}), neo4j_manager
        )
        self.fusion = RetrievalFusion(config.get('rag', {}))

        self._docs: Dict[str, Document] = {}
        self._initialized = False

    async def initialize(self):
        await self.vector_store.initialize()
        await self.kg_retriever.initialize()
        self._initialized = True
        print("[RAGService] Initialized successfully")

    async def import_document(self, file_path: str) -> Optional[Document]:
        """导入单个文档：解析 → 向量化 → 建图"""
        doc = await self.loader.load_file(file_path)
        if doc is None:
            return None

        self._docs[doc.id] = doc

        await self.vector_store.index_document(doc.id, doc.content, metadata={
            'filename': doc.filename,
            'file_type': doc.file_type,
            'char_count': len(doc.content),
            'chunk_count': len(doc.chunks)
        })

        await self.kg_retriever.extract_and_index(doc.id, doc.content)

        print(f"[RAGService] Imported document: {doc.filename} ({len(doc.chunks)} chunks)")
        return doc

    async def import_directory(self, dir_path: str) -> List[Document]:
        """批量导入目录下的文档"""
        docs = await self.loader.load_directory(dir_path)
        for doc in docs:
            self._docs[doc.id] = doc

        if docs:
            await self.vector_store.index_documents([
                {'id': d.id, 'text': d.content, 'metadata': {
                    'filename': d.filename, 'file_type': d.file_type
                }} for d in docs
            ])
            for doc in docs:
                await self.kg_retriever.extract_and_index(doc.id, doc.content)

        print(f"[RAGService] Imported {len(docs)} documents from '{dir_path}'")
        return docs

    async def search(
        self,
        query: str,
        top_k: int = None,
        fusion_method: str = 'rrf'
    ) -> Dict[str, Any]:
        """
        双路混合检索

        Args:
            query: 查询文本
            top_k: 返回结果数
            fusion_method: 融合方法 'rrf' / 'weighted'

        Returns:
            {'results': [...], 'sources': [...], 'context': '...'}
        """
        top_k = top_k or self.config.get('rag', {}).get('fusion_top_k', 5)

        vector_results_raw = await self.vector_store.search(query, top_k=top_k * 2)
        kg_results_raw = await self.kg_retriever.search_by_semantic(query, limit=top_k * 2)

        vector_results = [
            SearchResult(
                id=r.get('id', ''),
                text=r.get('text', ''),
                score=r.get('score', 0.0),
                source='vector',
                metadata=r.get('metadata', {})
            )
            for r in vector_results_raw
        ]

        kg_results = []
        for r in kg_results_raw.get('direct_matches', []):
            kg_results.append(SearchResult(
                id=r.get('id', ''),
                text=r.get('name', r.get('text', '')),
                score=0.8,  # 图匹配默认相关性
                source='knowledge_graph',
                metadata={'entity_label': r.get('label', '')}
            ))

        result_groups = {
            'vector': vector_results,
            'knowledge_graph': kg_results
        }

        if fusion_method == 'weighted':
            fused = self.fusion.weighted_fusion(result_groups, top_k=top_k)
        else:
            fused = self.fusion.rrf_fusion(result_groups, top_k=top_k)

        sources = []
        for r in fused:
            doc_id = r.metadata.get('doc_id', '')
            source_info = {'source': r.source, 'score': r.score, 'preview': r.highlight}
            if doc_id and doc_id in self._docs:
                source_info['document'] = self._docs[doc_id].filename
            sources.append(source_info)

        context = self.fusion.format_for_llm(fused, query)

        return {
            'query': query,
            'results': [{'id': r.id, 'text': r.text, 'score': r.score, 'source': r.source}
                        for r in fused],
            'sources': sources,
            'context': context,
            'total_found': len(fused)
        }

    async def answer_question(
        self,
        query: str,
        llm_client=None,
        max_sources: int = 5
    ) -> Dict[str, Any]:
        """端到端问答：检索 + LLM生成答案"""
        search_result = await self.search(query, top_k=max_sources)

        answer = None
        if llm_client:
            try:
                system_prompt = """你是一个专业的文档问答助手。请基于提供的参考文档回答用户问题。

要求：
1. 严格基于参考文档内容回答，不要编造信息
2. 如果参考文档不足以回答问题，明确告知用户
3. 引用具体文档来源
4. 回答简洁准确"""

                user_prompt = f"""参考文档：
{search_result['context']}

用户问题：{query}

请基于以上参考文档回答问题。"""

                answer = await llm_client.ainvoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ], temperature=0.3)
            except Exception as e:
                print(f"[RAGService] LLM answer generation failed: {e}")

        if answer is None:
            answer = self._build_fallback_answer(search_result)

        return {
            'query': query,
            'answer': answer,
            'sources': search_result['sources'][:max_sources],
            'total_docs_searched': search_result['total_found']
        }

    def _build_fallback_answer(self, search_result: dict) -> str:
        """无LLM时的回退答案构建"""
        results = search_result.get('results', [])
        if not results:
            return "抱歉，未找到与您问题相关的文档信息。"

        answer_parts = ["根据知识库检索，找到以下相关信息：\n"]
        for i, r in enumerate(results[:3], 1):
            answer_parts.append(f"{i}. {r['text'][:200]}... （相关度: {r['score']:.2f}）")
        return '\n'.join(answer_parts)

    async def incremental_update_document(self, doc_id: str, file_path: str):
        """文档增量更新"""
        new_doc = await self.loader.load_file(file_path)
        if new_doc is None:
            return

        self._docs[doc_id] = new_doc
        await self.vector_store.incremental_update(
            doc_id, new_doc.content,
            metadata={'filename': new_doc.filename, 'file_type': new_doc.file_type}
        )
        await self.kg_retriever.extract_and_index(doc_id, new_doc.content)
        print(f"[RAGService] Document '{doc_id}' updated incrementally")

    async def delete_document(self, doc_id: str):
        """删除文档及索引"""
        if doc_id in self._docs:
            del self._docs[doc_id]
        await self.vector_store.delete_document(doc_id)
        print(f"[RAGService] Document '{doc_id}' removed")

    def list_documents(self) -> List[dict]:
        """列出所有已索引文档"""
        return [doc.to_dict() for doc in self._docs.values()]

    async def get_document_preview(self, doc_id: str) -> Optional[dict]:
        """获取文档预览"""
        doc = self._docs.get(doc_id)
        return doc.to_dict() if doc else None
