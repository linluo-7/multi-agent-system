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
from ..monitoring.rag_tracer import RAGTracer
from .semantic_cache import SemanticCache


class RAGService:
    """双路混合RAG核心服务"""

    def __init__(self, config: dict, milvus_manager, neo4j_manager, embedding_service,
                 llm_client=None, redis_manager=None, metrics_collector=None):
        self.config = config
        self.milvus = milvus_manager
        self.neo4j = neo4j_manager
        self.embedding = embedding_service
        self.llm = llm_client
        self.query_rewriter = QueryRewriter(llm_client=llm_client, config=config.get('rag', {}))
        self.tracer = RAGTracer(redis_manager=redis_manager, metrics_collector=metrics_collector)
        self.cache = SemanticCache(redis_manager=redis_manager, config=config.get('rag', {}))

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

        # 语义缓存
        cached = await self.cache.get(query, kb_name)
        if cached:
            return cached

        # 链路追踪
        trace = self.tracer.start_trace(query, kb_name)

        # Query rewriting
        span_rewrite = trace.span('query_rewrite')
        rewrite_result = await self.query_rewriter.rewrite(
            query, history=history, use_hyde=use_hyde, decompose=decompose
        )
        search_query = rewrite_result.get('search_query', query)
        sub_queries = rewrite_result.get('sub_queries', [])
        span_rewrite.finish(hyde=rewrite_result.get('hyde_document') is not None,
                            decomposed=len(sub_queries) > 0)

        # 处理子问题：每个子问题分别检索再合并
        all_vector_raw = []
        all_kg_raw = {'direct_matches': [], 'expanded_paths': []}

        queries_to_search = [search_query]
        if decompose and sub_queries:
            queries_to_search = sub_queries[:3]  # 最多3个子问题

        for sq in queries_to_search:
            span_v = trace.span('vector_search')
            v_raw = await self.vector_store.search(
                sq, top_k=top_k * 2, collection=collection
            )
            trace.vector_latency_ms += span_v.duration_ms
            span_v.finish(hits=len(v_raw))

            span_kg = trace.span('kg_search')
            kg_raw = await self.kg_retriever.search_by_semantic(sq, limit=top_k * 2)
            trace.kg_latency_ms += span_kg.duration_ms
            span_kg.finish(hits=len(kg_raw.get('direct_matches', [])))

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
        span_sp = trace.span('sparse_search')
        sparse_raw = self.sparse_retriever.search(search_query, top_k=top_k * 2)
        trace.sparse_latency_ms = span_sp.duration_ms
        span_sp.finish(hits=len(sparse_raw))

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

        span_fusion = trace.span('fusion')
        if fusion_method == 'weighted':
            fused = self.fusion.weighted_fusion(result_groups, top_k=top_k)
        else:
            fused = self.fusion.rrf_fusion(result_groups, top_k=top_k)
        trace.fusion_latency_ms = span_fusion.duration_ms
        span_fusion.finish(candidates=len(fused))

        # Re-rank：LLM 或多样性重排
        span_rerank = trace.span('rerank')
        fused = await self.fusion.rerank_by_llm(fused, query, llm_client=self.llm, top_n=top_k)
        trace.rerank_latency_ms = span_rerank.duration_ms
        span_rerank.finish()

        # 父文档扩展：top结果获取更大上下文
        span_parent = trace.span('parent_doc_expand')
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

        span_parent.finish()
        context = self.fusion.format_for_llm(fused, query)

        trace.finish({'total_found': len(fused), 'results': [
            {'score': r.score} for r in fused
        ]})
        self.tracer.record_trace(trace)

        result = {
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

        # 写入缓存
        await self.cache.set(query, result, kb_name)
        return result

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
        kb_name: str = 'default',
        output_format: str = 'markdown',
        min_confidence: float = None
    ) -> Dict[str, Any]:
        """端到端问答：检索 + LLM生成答案（支持 inline citation、拒答降级、结构化输出）"""
        search_result = await self.search(query, top_k=max_sources, kb_name=kb_name)
        threshold = min_confidence or self.config.get('rag', {}).get('min_score', 0.5)

        results = search_result.get('results', [])
        has_good_results = any(r.get('score', 0) >= threshold for r in results)

        answer = None
        refusal_reason = None

        # 拒答判断
        if not has_good_results:
            refusal_reason = self._build_refusal(search_result, threshold)

        if not refusal_reason and llm_client:
            try:
                system_prompt = self._build_qa_system_prompt(output_format)
                user_prompt = self._build_qa_user_prompt(query, search_result, output_format)

                answer = await llm_client.ainvoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ], temperature=0.3)

                # 后处理：验证引用标注
                answer = self._postprocess_citations(answer, search_result)
            except Exception as e:
                print(f"[RAGService] LLM answer generation failed: {e}")

        if answer is None:
            if refusal_reason:
                answer = refusal_reason
            else:
                answer = self._build_fallback_answer(search_result)

        return {
            'query': query,
            'answer': answer,
            'sources': search_result['sources'][:max_sources],
            'total_docs_searched': search_result['total_found'],
            'confidence': self._estimate_confidence(results, threshold),
            'refused': not has_good_results and refusal_reason is not None,
            'output_format': output_format
        }

    def _build_qa_system_prompt(self, output_format: str = 'markdown') -> str:
        """构建带 inline citation 和结构化输出指令的系统提示词"""
        base = """你是专业的文档问答助手。严格基于参考文档回答用户问题。

核心规则：
1. 严格基于参考文档，不得编造
2. 每个关键事实必须标注来源编号，格式：[1] [2]
3. 如果文档信息不足，明确说明"文档中未找到相关信息"
4. 引用时使用方括号编号对应下方来源列表"""

        format_instructions = {
            'markdown': """\n输出格式：Markdown
- 使用标题、列表、加粗等组织答案
- 引用格式：[1]、[2-3]
- 末尾列出"📚 参考来源"编号列表""",

            'table': """\n输出格式：优先使用Markdown表格
- 数据对比类问题 → 表格呈现
- 每条数据标注引用编号""",

            'json': """\n输出格式：JSON
{
  "answer": "回答内容的markdown文本",
  "confidence": 0.85,
  "citations": [{"id": 1, "source": "文档名", "excerpt": "引用原文片段"}],
  "key_points": ["要点1", "要点2"]
}""",
        }

        return base + format_instructions.get(output_format, format_instructions['markdown'])

    def _build_qa_user_prompt(self, query: str, search_result: dict, output_format: str) -> str:
        """构建带编号来源的用户提示词"""
        sources = search_result.get('sources', [])
        context = search_result.get('context', '')

        # 构建带编号的来源列表
        numbered_sources = []
        for i, src in enumerate(sources, 1):
            doc_name = src.get('document', src.get('source', '未知'))
            preview = src.get('preview', '')[:100]
            numbered_sources.append(f"[{i}] {doc_name}: {preview}")

        sources_text = '\n'.join(numbered_sources) if numbered_sources else '无参考文档'

        prompt = f"""📄 参考文档：
{context}

📖 来源列表（答案中用 [编号] 引用）：
{sources_text}

❓ 用户问题：{query}

请基于以上参考文档和来源列表回答问题。每个关键事实后面标注来源编号。"""
        return prompt

    def _postprocess_citations(self, answer: str, search_result: dict) -> str:
        """后处理：确保引用格式正确，补充缺失的引用"""
        import re
        sources = search_result.get('sources', [])
        if not sources:
            return answer

        # 检查是否有引用标注
        has_citations = bool(re.search(r'\[\d+(?:[-,]\d+)*\]', answer))
        if not has_citations and sources:
            # 追加来源列表
            source_lines = ['\n\n📚 **参考来源**：']
            for i, src in enumerate(sources, 1):
                doc = src.get('document', src.get('source', '未知'))
                score = src.get('score', 0)
                source_lines.append(f"> [{i}] {doc} （相关度: {score:.0%}）")
            answer += '\n'.join(source_lines)
        return answer

    def _build_refusal(self, search_result: dict, threshold: float) -> str:
        """构建拒答回复"""
        results = search_result.get('results', [])
        kb_name = search_result.get('kb_name', '默认知识库')

        if not results:
            return (
                f"抱歉，未在 **{kb_name}** 中找到与您问题相关的文档信息。\n\n"
                f"建议：\n"
                f"- 尝试使用不同的关键词重新提问\n"
                f"- 确认文档已导入到正确的知识库\n"
                f"- 如需网络搜索，可使用搜索功能补充信息"
            )

        best_score = max(r.get('score', 0) for r in results)
        return (
            f"⚠️ 知识库中相关文档的匹配度较低（最高相关度 {best_score:.0%}，阈值 {threshold:.0%}）。\n\n"
            f"以下是可能相关的信息，请谨慎参考：\n\n"
            f"{self._build_fallback_answer(search_result)}\n\n"
            f"💡 建议尝试网络搜索获取更准确的信息。"
        )

    def _estimate_confidence(self, results: List[Dict], threshold: float) -> Dict[str, Any]:
        """估算答案置信度"""
        if not results:
            return {'level': 'none', 'score': 0.0, 'recommendation': 'refuse'}

        scores = [r.get('score', 0) for r in results]
        avg_score = sum(scores) / len(scores) if scores else 0
        max_score = max(scores) if scores else 0

        if max_score >= 0.8:
            level, rec = 'high', 'answer'
        elif max_score >= threshold:
            level, rec = 'medium', 'answer_with_caveat'
        elif avg_score >= threshold * 0.6:
            level, rec = 'low', 'answer_with_disclaimer'
        else:
            level, rec = 'insufficient', 'refuse_or_fallback'

        return {
            'level': level,
            'score': round(avg_score, 3),
            'max_score': round(max_score, 3),
            'recommendation': rec,
            'above_threshold': max_score >= threshold
        }

    def _build_fallback_answer(self, search_result: dict) -> str:
        """无LLM时的回退答案构建（带引用）"""
        results = search_result.get('results', [])
        sources = search_result.get('sources', [])
        if not results:
            return "抱歉，未找到与您问题相关的文档信息。"

        lines = ["根据知识库检索，找到以下相关信息：\n"]
        for i, r in enumerate(results[:3], 1):
            src_info = ''
            if i <= len(sources):
                doc = sources[i - 1].get('document', sources[i - 1].get('source', ''))
                if doc:
                    src_info = f" 📖 {doc}"
            lines.append(f"{i}. {r['text'][:300]}...\n   （相关度: {r['score']:.0%}{src_info}）")
        return '\n'.join(lines)

    async def stream_answer(
        self,
        query: str,
        llm_client=None,
        max_sources: int = 5,
        kb_name: str = 'default',
        min_confidence: float = None
    ):
        """流式问答：SSE 逐token返回答案"""
        search_result = await self.search(query, top_k=max_sources, kb_name=kb_name)
        threshold = min_confidence or self.config.get('rag', {}).get('min_score', 0.5)
        results = search_result.get('results', [])
        has_good = any(r.get('score', 0) >= threshold for r in results)

        # 发送搜索元数据
        yield {
            'type': 'search_complete',
            'total_found': search_result['total_found'],
            'sources': search_result.get('sources', [])[:max_sources],
            'confidence': self._estimate_confidence(results, threshold)
        }

        if not has_good:
            refusal = self._build_refusal(search_result, threshold)
            yield {'type': 'chunk', 'content': refusal}
            yield {'type': 'complete', 'refused': True}
            return

        if not llm_client:
            answer = self._build_fallback_answer(search_result)
            yield {'type': 'chunk', 'content': answer}
            yield {'type': 'complete', 'refused': False}
            return

        system_prompt = self._build_qa_system_prompt('markdown')
        user_prompt = self._build_qa_user_prompt(query, search_result, 'markdown')

        try:
            full_answer = ''
            async for chunk in llm_client.astream([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]):
                content = chunk if isinstance(chunk, str) else chunk.get('content', '')
                if content:
                    full_answer += content
                    yield {'type': 'chunk', 'content': content}

            full_answer = self._postprocess_citations(full_answer, search_result)
            yield {'type': 'complete', 'refused': False, 'full_answer': full_answer}
        except AttributeError:
            # LLM client 不支持 streaming，fallback
            answer = await llm_client.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.3)
            yield {'type': 'chunk', 'content': answer}
            yield {'type': 'complete', 'refused': False, 'full_answer': answer}
        except Exception as e:
            print(f"[RAGService] Stream failed: {e}")
            yield {'type': 'error', 'message': str(e)}

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

    # ---- ACL ----

    _acl: Dict[str, Dict[str, List[str]]] = {}  # {kb_name: {readers: [...], writers: [...]}}

    def set_acl(self, kb_name: str, readers: List[str] = None, writers: List[str] = None):
        """设置知识库权限"""
        if kb_name not in self._acl:
            self._acl[kb_name] = {'readers': [], 'writers': []}
        if readers is not None:
            self._acl[kb_name]['readers'] = readers
        if writers is not None:
            self._acl[kb_name]['writers'] = writers

    def check_access(self, kb_name: str, user: str, mode: str = 'read') -> bool:
        """检查用户对知识库的访问权限"""
        if kb_name not in self._acl:
            return True  # 无ACL限制，默认允许
        acl = self._acl[kb_name]
        allowed = acl.get('readers', []) if mode == 'read' else acl.get('writers', [])
        if not allowed:
            return True
        return user in allowed

    def get_acl(self, kb_name: str = None) -> dict:
        if kb_name:
            return self._acl.get(kb_name, {'readers': [], 'writers': []})
        return dict(self._acl)

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
