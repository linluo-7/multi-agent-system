"""
Redis Storage Layer
Redis存储层 - 负责实时状态管理
"""

import redis
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio


class RedisManager:
    """Redis实时状态管理类"""
    
    def __init__(self, config: dict):
        self.config = config
        self.key_prefix = config.get('key_prefix', 'mas')
        self.state_ttl = config.get('state_ttl', 3600)
        
        self.client = redis.Redis(
            host=config.get('host', 'localhost'),
            port=config.get('port', 6379),
            db=config.get('db', 0),
            password=config.get('password') or None,
            decode_responses=True
        )
        
        # 订阅相关
        self.pubsub = self.client.pubsub()
        self._subscribers: List[asyncio.Queue] = []
        
        print(f"[Redis] Connected to {config.get('host')}:{config.get('port')}")
    
    def _key(self, *parts) -> str:
        """生成带前缀的key"""
        return f"{self.key_prefix}:{':'.join(parts)}"
    
    # ========== Task State 操作 ==========
    
    def set_task_state(self, task_id: str, state: dict):
        """设置任务状态"""
        key = self._key('task', task_id, 'state')
        state['updated_at'] = datetime.now().isoformat()
        self.client.hset(key, mapping={k: json.dumps(v) for k, v in state.items()})
        self.client.expire(key, self.state_ttl)
        
        # 发布状态变更事件
        self._publish_event('task_state', {'task_id': task_id, 'state': state})
    
    def get_task_state(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        key = self._key('task', task_id, 'state')
        data = self.client.hgetall(key)
        if not data:
            return None
        return {k: json.loads(v) for k, v in data.items()}
    
    def update_task_state_field(self, task_id: str, field: str, value: Any):
        """更新任务状态的单个字段"""
        key = self._key('task', task_id, 'state')
        self.client.hset(key, field, json.dumps(value))
        self.client.expire(key, self.state_ttl)
        
        # 发布事件
        self._publish_event('task_update', {'task_id': task_id, 'field': field, 'value': value})
    
    def delete_task_state(self, task_id: str):
        """删除任务状态"""
        key = self._key('task', task_id, 'state')
        self.client.delete(key)
    
    # ========== Agent Status 操作 ==========
    
    def set_agent_status(self, agent_name: str, status: str, info: Optional[dict] = None):
        """设置Agent状态"""
        key = self._key('agent', agent_name, 'status')
        data = {
            'status': status,
            'updated_at': datetime.now().isoformat(),
            **(info or {})
        }
        self.client.hset(key, mapping={k: json.dumps(v) for k, v in data.items()})
        self.client.expire(key, self.state_ttl)
        
        # 发布事件
        self._publish_event('agent_status', {'agent': agent_name, 'status': status})
    
    def get_agent_status(self, agent_name: str) -> Optional[dict]:
        """获取Agent状态"""
        key = self._key('agent', agent_name, 'status')
        data = self.client.hgetall(key)
        if not data:
            return None
        return {k: json.loads(v) for k, v in data.items()}
    
    def get_all_agent_status(self) -> Dict[str, dict]:
        """获取所有Agent状态"""
        pattern = self._key('agent', '*', 'status')
        keys = self.client.keys(pattern)
        
        result = {}
        for key in keys:
            # 提取agent名称
            parts = key.split(':')
            if len(parts) >= 3:
                agent_name = parts[1]
                data = self.client.hgetall(key)
                if data:
                    result[agent_name] = {k: json.loads(v) for k, v in data.items()}
        return result
    
    def mark_agent_online(self, agent_name: str):
        """标记Agent上线"""
        self.set_agent_status(agent_name, 'online', {'last_seen': datetime.now().isoformat()})
    
    def mark_agent_offline(self, agent_name: str):
        """标记Agent离线"""
        self.set_agent_status(agent_name, 'offline', {'last_seen': datetime.now().isoformat()})
    
    def mark_agent_busy(self, agent_name: str, task_id: str):
        """标记Agent忙碌（正在执行任务）"""
        self.set_agent_status(agent_name, 'busy', {
            'task_id': task_id,
            'started_at': datetime.now().isoformat()
        })
    
    def mark_agent_idle(self, agent_name: str):
        """标记Agent空闲"""
        self.set_agent_status(agent_name, 'online', {'last_seen': datetime.now().isoformat()})
    
    # ========== Blackboard（共享中间结果）操作 ==========
    
    def write_to_blackboard(self, task_id: str, agent_name: str, data: dict):
        """向黑板写入数据（Agent间共享）"""
        key = self._key('blackboard', task_id)
        
        # 获取现有数据
        existing = self.client.hgetall(key)
        existing = {k: json.loads(v) for k, v in existing.items()} if existing else {}
        
        # 追加新数据
        timestamp = datetime.now().isoformat()
        existing[agent_name] = {
            'data': data,
            'timestamp': timestamp
        }
        
        # 写入
        self.client.hset(key, mapping={k: json.dumps(v) for k, v in existing.items()})
        self.client.expire(key, self.state_ttl * 2)  # 黑板保留更长时间
        
        # 发布事件
        self._publish_event('blackboard_write', {
            'task_id': task_id,
            'agent': agent_name,
            'data_keys': list(data.keys()) if isinstance(data, dict) else ['value']
        })
    
    def read_from_blackboard(self, task_id: str) -> Dict[str, dict]:
        """从黑板读取所有数据"""
        key = self._key('blackboard', task_id)
        data = self.client.hgetall(key)
        if not data:
            return {}
        return {k: json.loads(v) for k, v in data.items()}
    
    def read_from_blackboard_agent(self, task_id: str, agent_name: str) -> Optional[dict]:
        """从黑板读取特定Agent的数据"""
        key = self._key('blackboard', task_id)
        data = self.client.hget(key, agent_name)
        if not data:
            return None
        return json.loads(data)
    
    def clear_blackboard(self, task_id: str):
        """清空黑板"""
        key = self._key('blackboard', task_id)
        self.client.delete(key)
    
    # ========== 消息队列操作 ==========
    
    def enqueue_message(self, queue_name: str, message: dict):
        """入队消息"""
        key = self._key('queue', queue_name)
        self.client.rpush(key, json.dumps(message))
        
        # 发布事件
        self._publish_event('queue_enqueue', {'queue': queue_name})
    
    def dequeue_message(self, queue_name: str, timeout: int = 0) -> Optional[dict]:
        """出队消息（阻塞）"""
        key = self._key('queue', queue_name)
        result = self.client.blpop(key, timeout=timeout)
        if result:
            _, value = result
            return json.loads(value)
        return None
    
    def get_queue_length(self, queue_name: str) -> int:
        """获取队列长度"""
        key = self._key('queue', queue_name)
        return self.client.llen(key)
    
    # ========== Pub/Sub 事件发布 ==========
    
    def _publish_event(self, event_type: str, data: dict):
        """发布事件到订阅频道"""
        channel = self._key('events', event_type)
        message = json.dumps({
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
        self.client.publish(channel, message)
    
    async def subscribe(self, event_types: List[str]) -> asyncio.Queue:
        """订阅事件（异步）"""
        queue = asyncio.Queue()
        self._subscribers.append(queue)
        
        channels = [self._key('events', et) for et in event_types]
        self.pubsub.subscribe(*channels)
        
        async def listen():
            for item in self.pubsub.listen():
                if item['type'] == 'message':
                    try:
                        data = json.loads(item['data'])
                        await queue.put(data)
                    except json.JSONDecodeError:
                        continue
        
        asyncio.create_task(listen())
        return queue
    
    # ========== 协作状态快照 ==========
    
    def get_collaboration_snapshot(self, task_id: str) -> dict:
        """获取任务协作快照"""
        return {
            'task_state': self.get_task_state(task_id),
            'blackboard': self.read_from_blackboard(task_id),
            'agents': self.get_all_agent_status()
        }
    
    def close(self):
        """关闭连接"""
        self.pubsub.close()
        self.client.close()
        print("[Redis] Connection closed")


# 全局实例
_redis_instance: Optional[RedisManager] = None


def get_redis(config: dict) -> RedisManager:
    """获取或创建Redis实例"""
    global _redis_instance
    if _redis_instance is None:
        _redis_instance = RedisManager(config)
    return _redis_instance
