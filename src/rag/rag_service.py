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
from .query_rewriter import QueryRewriter
from .sparse_retriever import SparseRetriever


class RAGService:
    """双路混合RAG核心服务"""

    def __init__(self, config: dict, milvus_manager, neo4j_manager, embedding_service,
                 llm_client=None):
        self.config = config
        self.milvus = milvus_manager
        self.neo4j = neo4j_manager
        self.embedding = embedding_service
        self.llm = llm_client
        self.query_rewriter = QueryRewriter(llm_client=llm_client, config=config.get('rag', {}))

        self.loader = DocumentLoader(config.get('rag', {}))
        self.vector_store = VectorStore(
            config.get('rag', {}), milvus_manager, embedding_service
        )
        self.kg_retriever = KnowledgeGraphRetriever(
            config.get('rag', {}), neo4j_manager, llm_client=llm_client
        )
        self.sparse_retriever = SparseRetriever(config.get('rag', {}))
        self.fusion = RetrievalFusion(config.get('rag', {}))

        self._docs: Dict[str, Document] = {}
        self._kb_docs: Dict[str, Dict[str, Document]] = {}  # kb_name -> {doc_id: Document}
        self._kbs = config.get('rag', {}).get('knowledge_bases', {'default': {'collection': 'documents'}})
        self._initialized = False

    async def initialize(self):
        await self.vector_store.initialize()
        await self.kg_retriever.initialize()
        self._initialized = True
        print("[RAGService] Initialized successfully")

    def _get_collection(self, kb_name: str = None) -> str:
        """根据知识库名获取对应的 collection 名称"""
        kb_name = kb_name or 'default'
        kb = self._kbs.get(kb_name, self._kbs.get('default', {'collection': 'documents'}))
        return kb.get('collection', 'documents')

    async def import_document(self, file_path: str, kb_name: str = 'default') -> Optional[Document]:
        """导入单个文档到指定知识库：解析 → 向量化 → 建图"""
        doc = await self.loader.load_file(file_path)
        if doc is None:
            return None

        self._docs[doc.id] = doc
        self._kb_docs.setdefault(kb_name, {})[doc.id] = doc

        # 向量索引
        collection = self._get_collection(kb_name)
        await self.vector_store.index_document(doc.id, doc.content, metadata={
            'filename': doc.filename,
            'file_type': doc.file_type,
            'char_count': len(doc.content),
            'chunk_count': len(doc.chunks),
            'kb_name': kb_name
        }, collection=collection)

        # 稀疏检索索引
        self.sparse_retriever.index_document(doc.id, doc.content, metadata={
            'filename': doc.filename, 'file_type': doc.file_type, 'kb_name': kb_name
        })

        await self.kg_retriever.extract_and_index(doc.id, doc.content)

        print(f"[RAGService] Imported document: {doc.filename} → kb={kb_name} "
              f"({len(doc.chunks)} chunks)")
        return doc

    async def import_directory(self, dir_path: str, kb_name: str = 'default') -> List[Document]:
        """批量导入目录下的文档到指定知识库"""
        docs = await self.loader.load_directory(dir_path)
        for doc in docs:
            self._docs[doc.id] = doc
            self._kb_docs.setdefault(kb_name, {})[doc.id] = doc

        collection = self._get_collection(kb_name)
        if docs:
            await self.vector_store.index_documents([
                {'id': d.id, 'text': d.content, 'metadata': {
                    'filename': d.filename, 'file_type': d.file_type, 'kb_name': kb_name
                }} for d in docs
            ], collection=collection)
            for doc in docs:
                await self.kg_retriever.extract_and_index(doc.id, doc.content)

        print(f"[RAGService] Imported {len(docs)} documents from '{dir_path}' → kb={kb_name}")
        return docs

    async def search(
        self,
        query: str,
        top_k: int = None,
        fusion_method: str = 'rrf',
        kb_name: str = 'default',
        history: List[Dict] = None,
        use_hyde: bool = False,
        decompose: bool = False
    ) -> Dict[str, Any]:
        """
        双路混合检索，支持查询改写和多知识库

        Args:
            query: 查询文本
            top_k: 返回结果数
            fusion_method: 融合方法 'rrf' / 'weighted'
            kb_name: 知识库名称
            history: 对话历史（用于多轮上下文改写）
            use_hyde: 是否使用 HyDE 假设文档增强
            decompose: 是否拆解子问题

        Returns:
            {'results': [...], 'sources': [...], 'context': '...'}
        """
        top_k = top_k or self.config.get('rag', {}).get('fusion_top_k', 5)
        collection = self._get_collection(kb_name)

        # Query rewriting
        rewrite_result = await self.query_rewriter.rewrite(
            query, history=history, use_hyde=use_hyde, decompose=decompose
        )
        search_query = rewrite_result.get('search_query', query)
        sub_queries = rewrite_result.get('sub_queries', [])

        # 处理子问题：每个子问题分别检索再合并
        all_vector_raw = []
        all_kg_raw = {'direct_matches': [], 'expanded_paths': []}

        queries_to_search = [search_query]
        if decompose and sub_queries:
            queries_to_search = sub_queries[:3]  # 最多3个子问题

        for sq in queries_to_search:
            v_raw = await self.vector_store.search(
                sq, top_k=top_k * 2, collection=collection
            )
            kg_raw = await self.kg_retriever.search_by_semantic(sq, limit=top_k * 2)
            all_vector_raw.extend(v_raw)
            all_kg_raw['direct_matches'].extend(kg_raw.get('direct_matches', []))
            all_kg_raw['expanded_paths'].extend(kg_raw.get('expanded_paths', []))

        # 去重
        seen_v = set()
        vector_results_raw = []
        for r in all_vector_raw:
            if r.get('id') not in seen_v:
                seen_v.add(r.get('id'))
                vector_results_raw.append(r)

        kg_results_raw = all_kg_raw

        # 稀疏检索 (BM25)
        sparse_raw = self.sparse_retriever.search(search_query, top_k=top_k * 2)

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
            'knowledge_graph': kg_results,
            'sparse': [
                SearchResult(
                    id=r.get('id', ''),
                    text=r.get('text', ''),
                    score=min(r.get('score', 0.0), 1.0),
                    source='bm25',
                    metadata=r.get('metadata', {})
                )
                for r in sparse_raw
            ]
        }

        if fusion_method == 'weighted':
            fused = self.fusion.weighted_fusion(result_groups, top_k=top_k)
        else:
            fused = self.fusion.rrf_fusion(result_groups, top_k=top_k)

        # Re-rank：LLM 或多样性重排
        fused = await self.fusion.rerank_by_llm(fused, query, llm_client=self.llm, top_n=top_k)

        # 父文档扩展：top结果获取更大上下文
        top_results = [{'id': r.id, 'text': r.text, 'score': r.score,
                        'metadata': r.metadata, 'highlight': r.highlight}
                       for r in fused]
        expanded = await self.expand_to_parent_documents(top_results)
        # 将 parent_context 合并回 SearchResult
        for f, e in zip(fused, expanded):
            if 'parent_context' in e:
                f.metadata['parent_context'] = e['parent_context']
                f.metadata['parent_document'] = e.get('parent_document', '')

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
            'search_query': search_query,
            'rewritten': rewrite_result.get('rewritten', query),
            'hyde_used': use_hyde and rewrite_result.get('hyde_document') is not None,
            'sub_queries': sub_queries,
            'kb_name': kb_name,
            'results': [{'id': r.id, 'text': r.text, 'score': r.score, 'source': r.source}
                        for r in fused],
            'sources': sources,
            'context': context,
            'total_found': len(fused)
        }

    async def multi_hop_search(
        self,
        query: str,
        max_hops: int = 2,
        top_k: int = None,
        kb_name: str = 'default'
    ) -> Dict[str, Any]:
        """
        多跳检索：首轮检索 → 提取关键信息 → 第二轮检索

        适用场景：需要关联多个事实来回答的复杂问题
        """
        top_k = top_k or self.config.get('rag', {}).get('fusion_top_k', 5)
        all_results = {}
        all_sources = []
        hop_history = []

        current_query = query
        for hop in range(max_hops):
            result = await self.search(
                current_query, top_k=top_k, kb_name=kb_name, decompose=False
            )

            hop_info = {
                'hop': hop + 1,
                'query': current_query,
                'results': len(result.get('results', [])),
                'total_found': result.get('total_found', 0)
            }
            hop_history.append(hop_info)

            # 累积结果
            for r in result.get('results', []):
                key = r['id']
                if key not in all_results or r['score'] > all_results[key]['score']:
                    all_results[key] = r
            all_sources.extend(result.get('sources', []))

            # 最后一跳不需要再生成 query
            if hop == max_hops - 1:
                break

            # 用首轮结果生成下一跳查询
            context_snippet = result.get('context', '')[:500]
            next_query = await self._generate_next_hop_query(query, context_snippet, hop + 1)
            if not next_query:
                break
            current_query = next_query

        merged = sorted(all_results.values(), key=lambda x: x['score'], reverse=True)

        return {
            'query': query,
            'hops': hop_history,
            'results': merged[:top_k],
            'sources': all_sources[:top_k * 2],
            'total_found': len(all_results),
            'kb_name': kb_name
        }

    async def _generate_next_hop_query(
        self, original_query: str, context: str, hop: int
    ) -> Optional[str]:
        """根据首轮检索结果生成下一跳查询"""
        if not self.llm or not context.strip():
            return None

        try:
            prompt = f"""原始问题：{original_query}

首轮检索结果摘要：
{context[:500]}

基于以上结果，生成一个新的搜索查询，用于获取补充信息或更详细的答案。
只输出查询文本，不要其他内容。"""
            response = await self.llm.ainvoke([
                {"role": "user", "content": prompt}
            ], temperature=0.3)
            next_query = response.strip().strip('"').strip("'")
            if len(next_query) > 5:
                print(f"[RAGService] Hop-{hop} generated query: {next_query[:80]}")
                return next_query
        except Exception as e:
            print(f"[RAGService] Hop query generation failed: {e}")
        return None

    async def answer_question(
        self,
        query: str,
        llm_client=None,
        max_sources: int = 5,
        kb_name: str = 'default'
    ) -> Dict[str, Any]:
        """端到端问答：检索 + LLM生成答案"""
        search_result = await self.search(query, top_k=max_sources, kb_name=kb_name)

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

    def list_documents(self, kb_name: str = None) -> List[dict]:
        """列出已索引文档，可按知识库筛选"""
        if kb_name and kb_name in self._kb_docs:
            return [doc.to_dict() for doc in self._kb_docs[kb_name].values()]
        return [doc.to_dict() for doc in self._docs.values()]

    async def expand_to_parent_documents(
        self,
        results: List[Dict],
        max_context_chars: int = 2000
    ) -> List[Dict]:
        """
        父文档检索：将 chunk 级检索结果扩展为父文档上下文

        用小块检索（精确匹配），返回大块上下文（完整段落/文档）
        """
        for r in results:
            doc_id = r.get('metadata', {}).get('doc_id', '')
            if not doc_id or doc_id not in self._docs:
                continue

            doc = self._docs[doc_id]
            chunk_idx = r.get('metadata', {}).get('chunk_index', 0)
            total_chunks = r.get('metadata', {}).get('total_chunks', 1)

            # 取当前块前后各1个块作为扩展上下文
            start_idx = max(0, chunk_idx - 1)
            end_idx = min(total_chunks, chunk_idx + 2)

            # 构建扩展文本：前序块 + 当前块 + 后续块
            parent_chunks = doc.chunks[start_idx:end_idx]

            if doc.chunks and chunk_idx < len(doc.chunks):
                current_chunk = doc.chunks[chunk_idx]
                # 在原始文档中找到块的更大上下文
                chunk_pos = doc.content.find(current_chunk[:100])
                if chunk_pos >= 0:
                    context_start = max(0, chunk_pos - max_context_chars // 3)
                    context_end = min(len(doc.content),
                                      chunk_pos + max_context_chars * 2 // 3)
                    r['parent_context'] = doc.content[context_start:context_end]
                else:
                    r['parent_context'] = '\n'.join(parent_chunks)

            r['parent_document'] = doc.filename
            r['parent_chunks'] = [{'idx': i, 'text': c[:200]}
                                  for i, c in enumerate(parent_chunks)]

        return results

    def list_knowledge_bases(self) -> List[dict]:
        """列出所有知识库及其文档数"""
        return [
            {'name': name, 'collection': cfg.get('collection', ''),
             'description': cfg.get('description', ''), 'doc_count': len(self._kb_docs.get(name, {}))}
            for name, cfg in self._kbs.items()
        ]

    async def get_document_preview(self, doc_id: str) -> Optional[dict]:
        """获取文档预览"""
        doc = self._docs.get(doc_id)
        return doc.to_dict() if doc else None
