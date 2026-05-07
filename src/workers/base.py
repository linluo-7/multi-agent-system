"""
Base Worker
工作Agent基类 - 所有具体Agent的父类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import asyncio
import json


class BaseWorker(ABC):
    """工作Agent基类"""
    
    # 类属性，子类必须覆盖
    name: str = "base_worker"
    description: str = "基础工作Agent"
    
    def __init__(self, config: dict, redis_manager, postgres_storage):
        self.config = config
        self.redis = redis_manager
        self.storage = postgres_storage
        self._running = False
        self._current_task: Optional[Dict] = None
    
    async def initialize(self):
        """初始化Agent"""
        self._running = True
        self.redis.mark_agent_online(self.name)
        print(f"[{self.name}] Agent initialized and online")
    
    async def shutdown(self):
        """关闭Agent"""
        self._running = False
        self.redis.mark_agent_offline(self.name)
        print(f"[{self.name}] Agent shutdown")
    
    async def execute_task(self, task: dict, context: dict) -> dict:
        """
        执行任务的入口方法
        
        Args:
            task: 任务定义，包含 type, input, constraints 等
            context: 执行上下文，包含对话历史、黑板数据等
        
        Returns:
            执行结果字典
        """
        task_id = task.get('id', 'unknown')
        
        # 更新状态为执行中
        self.redis.mark_agent_busy(self.name, task_id)
        self._current_task = task
        
        try:
            # 保存开始日志
            self.storage.save_audit_log(
                'task_start',
                self.name,
                {'task_id': task_id, 'task_type': task.get('type')}
            )
            
            # 执行业务逻辑
            result = await self.execute(task, context)
            
            # 更新状态为完成
            self.redis.mark_agent_idle(self.name)
            
            # 写入黑板共享结果
            self.redis.write_to_blackboard(task_id, self.name, result)
            
            # 保存完成日志
            self.storage.save_audit_log(
                'task_complete',
                self.name,
                {'task_id': task_id, 'result_keys': list(result.keys()) if isinstance(result, dict) else ['value']}
            )
            
            return result
            
        except Exception as e:
            # 错误处理
            error_result = {
                'error': str(e),
                'error_type': type(e).__name__,
                'timestamp': datetime.now().isoformat()
            }
            
            self.redis.mark_agent_idle(self.name)
            
            self.storage.save_audit_log(
                'task_error',
                self.name,
                {'task_id': task_id, 'error': str(e)}
            )
            
            return error_result
        finally:
            self._current_task = None
    
    @abstractmethod
    async def execute(self, task: dict, context: dict) -> dict:
        """
        子类实现的具体执行逻辑
        
        Args:
            task: 任务定义
            context: 执行上下文
        
        Returns:
            执行结果
        """
        pass
    
    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self.config.get('system_prompt', f'You are a {self.name} agent.')
    
    def get_status(self) -> dict:
        """获取Agent状态"""
        return {
            'name': self.name,
            'status': 'busy' if self._current_task else 'idle',
            'current_task': self._current_task.get('id') if self._current_task else None,
            'config': {
                'model': self.config.get('model'),
                'temperature': self.config.get('temperature')
            }
        }


class MockLLM:
    """模拟LLM调用（用于测试和开发）"""
    
    def __init__(self, model: str = "mock", temperature: float = 0.7):
        self.model = model
        self.temperature = temperature
    
    async def ainvoke(self, messages: list) -> str:
        """异步调用LLM"""
        await asyncio.sleep(0.1)  # 模拟延迟
        
        # 简单返回输入的摘要
        last_message = messages[-1] if messages else {}
        content = last_message.get('content', '')
        
        return f"[Mock Response] Received: {content[:100]}..."
    
    async def invoke(self, prompt: str) -> str:
        """同步调用LLM"""
        return await self.ainvoke([{'role': 'user', 'content': prompt}])
