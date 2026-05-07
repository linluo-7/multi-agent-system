"""
Search Agent
搜索Agent - 负责网络搜索和信息获取
"""

import asyncio
from typing import Dict, Any
from .base import BaseWorker

# Tavily API Client
try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False


class SearchAgent(BaseWorker):
    """网络搜索Agent"""
    
    name = "search"
    description = "网络搜索Agent，负责搜索和获取网络信息"
    
    def __init__(self, config: dict, redis_manager, postgres_storage):
        super().__init__(config, redis_manager, postgres_storage)
        self.max_results = config.get('max_results', 5)
        self.tavily_client = None
        
        # 初始化 Tavily 客户端
        if TAVILY_AVAILABLE:
            tavily_config = config.get('tavily', {})
            api_key = tavily_config.get('api_key')
            if api_key:
                try:
                    self.tavily_client = TavilyClient(api_key=api_key)
                    print(f"[SearchAgent] Tavily client initialized")
                except Exception as e:
                    print(f"[SearchAgent] Failed to initialize Tavily: {e}")
    
    async def execute(self, task: dict, context: dict) -> dict:
        """
        执行搜索任务
        
        Expected task format:
        {
            "type": "search",
            "input": {
                "query": "搜索关键词",
                "source": "web" | "news" | "academic"  # optional
            }
        }
        """
        task_input = task.get('input', {})
        query = task_input.get('query', '')
        
        if not query:
            return {'error': 'No query provided', 'results': []}
        
        # 从上下文获取历史信息（避免重复搜索）
        blackboard = context.get('blackboard', {})
        previous_searches = [
            v.get('data', {}).get('query') 
            for k, v in blackboard.items() 
            if k.startswith('search')
        ]
        
        # 如果已经搜索过相同查询，直接返回缓存结果
        if query in previous_searches:
            return {
                'query': query,
                'results': [],
                'source': 'cache',
                'count': 0,
                'context_summary': '（使用缓存结果）'
            }
        
        # 调用搜索API
        if self.tavily_client:
            results = await self._search_tavily(query)
        else:
            results = await self._mock_search_results(query)
        
        return {
            'query': query,
            'results': results,
            'source': 'tavily' if self.tavily_client else 'mock',
            'count': len(results),
            'context_summary': self._summarize_results(results)
        }
    
    async def _search_tavily(self, query: str) -> list:
        """
        使用 Tavily AI 搜索
        
        Tavily 是专为 LLM/AI 场景设计的搜索API，
        返回结构化的搜索结果。
        """
        try:
            # Tavily SDK 本身是同步的，需要在线程池中运行
            loop = asyncio.get_event_loop()
            
            def sync_search():
                response = self.tavily_client.search(
                    query=query,
                    search_depth=self.config.get('tavily', {}).get('search_depth', 'basic'),
                    max_results=self.max_results
                )
                return response
            
            response = await loop.run_in_executor(None, sync_search)
            
            # 解析 Tavily 响应
            results = []
            for item in response.get('results', []):
                results.append({
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'snippet': item.get('content', ''),
                    'relevance': item.get('score', 0.0)
                })
            
            print(f"[SearchAgent] Tavily search returned {len(results)} results for '{query}'")
            return results
            
        except Exception as e:
            print(f"[SearchAgent] Tavily search failed: {e}")
            # 降级到 Mock
            return await self._mock_search_results(query)
    
    async def _mock_search_results(self, query: str) -> list:
        """模拟搜索结果（开发测试用 / Tavily不可用时降级）"""
        await asyncio.sleep(0.1)  # 模拟网络延迟
        
        return [
            {
                'title': f'关于"{query}"的重要信息',
                'url': f'https://example.com/search?q={query}',
                'snippet': f'这是关于{query}的搜索结果摘要，包含相关技术信息和最佳实践...',
                'relevance': 0.95
            },
            {
                'title': f'{query} - 官方文档',
                'url': f'https://example.com/docs/{query}',
                'snippet': f'{query}的官方技术文档，详细介绍了使用方法...',
                'relevance': 0.90
            },
            {
                'title': f'{query} 实战教程',
                'url': f'https://example.com/tutorial/{query}',
                'snippet': f'从入门到精通的{query}实战教程，包含大量示例代码...',
                'relevance': 0.85
            }
        ]
    
    def _summarize_results(self, results: list) -> str:
        """生成结果摘要"""
        if not results:
            return "未找到相关结果"
        
        summary_parts = []
        for r in results[:3]:
            title = r.get('title', '')
            snippet = r.get('snippet', '')[:50]
            summary_parts.append(f"• {title}: {snippet}...")
        
        return '\n'.join(summary_parts)
