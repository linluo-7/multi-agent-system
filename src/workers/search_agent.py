"""
Search Agent
搜索Agent - 负责网络搜索和信息获取
"""

import httpx
from typing import Dict, Any
from .base import BaseWorker


class SearchAgent(BaseWorker):
    """网络搜索Agent"""
    
    name = "search"
    description = "网络搜索Agent，负责搜索和获取网络信息"
    
    def __init__(self, config: dict, redis_manager, postgres_storage):
        super().__init__(config, redis_manager, postgres_storage)
        self.max_results = config.get('max_results', 5)
    
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
        
        # 调用搜索API（这里用DuckDuckGo示例）
        results = await self._search_duckduckgo(query)
        
        return {
            'query': query,
            'results': results,
            'source': 'duckduckgo',
            'count': len(results),
            'context_summary': self._summarize_results(results)
        }
    
    async def _search_duckduckgo(self, query: str) -> list:
        """
        使用DuckDuckGo搜索
        
        注意：生产环境建议使用 Tavily API 或 Google Custom Search API
        这里用 httpx 简单封装，实际项目中可替换为付费/免费API
        """
        try:
            # 使用公共搜索API（示例用serpapi或其他免费API）
            # 这里暂时返回模拟数据，实际使用时替换为真实API
            async with httpx.AsyncClient(timeout=10.0) as client:
                # TODO: 替换为真实搜索API
                # 示例: response = await client.get("https://api.search.com/search", params={"q": query})
                
                # 模拟返回
                return await self._mock_search_results(query)
                
        except Exception as e:
            return [{
                'title': f'搜索结果: {query}',
                'url': '',
                'snippet': f'搜索失败: {str(e)}',
                'error': True
            }]
    
    async def _mock_search_results(self, query: str) -> list:
        """模拟搜索结果（开发测试用）"""
        await asyncio.sleep(0.05)  # 模拟网络延迟
        
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


import asyncio  # 需要这个才能使用 asyncio.sleep
