"""
RAG Agent
RAG检索Agent — 负责文档检索和知识问答
"""
import json
from typing import Dict, Any
from .base import BaseWorker


class RAGAgent(BaseWorker):

    name = "rag"
    description = "RAG检索Agent，负责文档检索和知识问答"

    def __init__(self, config: dict, redis_manager, postgres_storage,
                 rag_service=None, llm_client=None):
        super().__init__(config, redis_manager, postgres_storage)
        self.rag = rag_service
        self.llm = llm_client

    async def execute(self, task: dict, context: dict) -> dict:
        task_input = task.get('input', {})
        action = task_input.get('action', 'search')
        query = task_input.get('query', '')

        if not query:
            return {'error': 'No query provided', 'results': []}

        if action == 'qa':
            return await self._do_qa(query, task_input)
        else:
            return await self._do_search(query, task_input)

    async def _do_search(self, query: str, task_input: dict) -> dict:
        top_k = task_input.get('top_k', None)
        fusion_method = task_input.get('fusion_method', 'rrf')

        try:
            result = await self.rag.search(query, top_k=top_k, fusion_method=fusion_method)
        except Exception as e:
            return {'error': str(e), 'query': query, 'results': []}

        return {
            'query': query,
            'results': result.get('results', []),
            'sources': result.get('sources', []),
            'total_found': result.get('total_found', 0),
            'context': result.get('context', ''),
            'needs_fallback': len(result.get('results', [])) == 0 or all(
                r.get('score', 0) < 0.5 for r in result.get('results', [])
            )
        }

    async def _do_qa(self, query: str, task_input: dict) -> dict:
        max_sources = task_input.get('max_sources', 5)

        try:
            result = await self.rag.answer_question(
                query, llm_client=self.llm, max_sources=max_sources
            )
        except Exception as e:
            return {'error': str(e), 'query': query, 'answer': ''}

        return {
            'query': query,
            'answer': result.get('answer', ''),
            'sources': result.get('sources', []),
            'total_docs_searched': result.get('total_docs_searched', 0),
            'needs_fallback': result.get('total_docs_searched', 0) == 0
        }

    def get_system_prompt(self) -> str:
        return self.config.get(
            'system_prompt',
            '你是一个专业的RAG检索Agent。你的职责是：\n'
            '1. 理解用户查询意图\n'
            '2. 执行向量检索和知识图谱检索\n'
            '3. 融合多路检索结果\n'
            '4. 基于检索结果生成准确答案\n'
            '始终引用检索到的来源，保证答案的可追溯性。'
        )
