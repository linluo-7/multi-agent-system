"""
LLM Client
MiniMax LLM 客户端 - 使用 Anthropic Messages API
"""

import asyncio
import httpx
from typing import List, Dict, Any, Optional


class MiniMaxClient:
    """MiniMax API 客户端（Anthropic Messages API 格式）"""
    
    def __init__(self, config: dict):
        self.config = config
        self.api_key = config.get('api_key')
        self.base_url = config.get('base_url', 'https://api.minimaxi.com/anthropic').rstrip('/')
        self.model = config.get('model', 'MiniMax-M2')
        self.temperature = config.get('temperature', 0.7)
        
        print(f"[MiniMax] Client initialized with model: {self.model}")
        print(f"[MiniMax] Base URL: {self.base_url}")
    
    async def ainvoke(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        异步调用 LLM
        
        Args:
            messages: [{"role": "user"/"assistant"/"system", "content": "..."}]
            **kwargs: temperature, max_tokens 等
        
        Returns:
            LLM 响应的文本内容
        """
        try:
            loop = asyncio.get_event_loop()
            
            def sync_call():
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(
                        f"{self.base_url}/v1/messages",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "x-api-key": self.api_key,
                            "anthropic-version": "2023-06-01"
                        },
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": kwargs.get('temperature', self.temperature),
                            "max_tokens": kwargs.get('max_tokens', 4096)
                        }
                    )
                    
                    if response.status_code != 200:
                        raise Exception(f"API Error: {response.status_code} - {response.text}")
                    
                    result = response.json()
                    # 返回 content 中的文本
                    if result.get('content') and len(result['content']) > 0:
                        return result['content'][0].get('text', '')
                    return str(result)
            
            result = await loop.run_in_executor(None, sync_call)
            return result
            
        except Exception as e:
            print(f"[MiniMax] API call failed: {e}")
            raise
    
    def invoke(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """同步调用"""
        return asyncio.get_event_loop().run_until_complete(self.ainvoke(messages, **kwargs))


# 全局实例
_llm_client: Optional[MiniMaxClient] = None


def get_llm(config: dict) -> MiniMaxClient:
    """获取或创建 LLM 客户端"""
    global _llm_client
    if _llm_client is None:
        _llm_client = MiniMaxClient(config)
    return _llm_client
