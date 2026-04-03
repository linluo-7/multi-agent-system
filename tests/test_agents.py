"""
Tests for Multi-Agent System
多Agent系统测试
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock


class MockRedis:
    """模拟Redis"""
    def __init__(self):
        self.data = {}
    
    def _key(self, *parts):
        return ':'.join(parts)
    
    def set_task_state(self, task_id, state):
        key = self._key('mas', 'task', task_id, 'state')
        self.data[key] = state
    
    def get_task_state(self, task_id):
        key = self._key('mas', 'task', task_id, 'state')
        return self.data.get(key)
    
    def mark_agent_online(self, name):
        key = self._key('mas', 'agent', name, 'status')
        self.data[key] = {'status': 'online'}
    
    def mark_agent_busy(self, name, task_id):
        key = self._key('mas', 'agent', name, 'status')
        self.data[key] = {'status': 'busy', 'task_id': task_id}
    
    def mark_agent_idle(self, name):
        key = self._key('mas', 'agent', name, 'status')
        self.data[key] = {'status': 'online'}
    
    def get_agent_status(self, name):
        key = self._key('mas', 'agent', name, 'status')
        return self.data.get(key)
    
    def write_to_blackboard(self, task_id, agent, data):
        key = self._key('mas', 'blackboard', task_id)
        if key not in self.data:
            self.data[key] = {}
        self.data[key][agent] = {'data': data}
    
    def read_from_blackboard(self, task_id):
        key = self._key('mas', 'blackboard', task_id)
        return self.data.get(key, {})
    
    def update_task_state_field(self, task_id, field, value):
        key = self._key('mas', 'task', task_id, 'state')
        if key not in self.data:
            self.data[key] = {}
        self.data[key][field] = value


class MockStorage:
    """模拟PostgreSQL存储"""
    def __init__(self):
        self.conversations = {}
        self.tasks = {}
        self.messages = []
        self.audit_logs = []
    
    def create_conversation(self, title):
        conv_id = 'conv_' + str(len(self.conversations))
        self.conversations[conv_id] = {
            'id': conv_id,
            'title': title,
            'created_at': 'now',
            'updated_at': 'now'
        }
        return conv_id
    
    def create_task(self, conversation_id, task_type, payload):
        task_id = 'task_' + str(len(self.tasks))
        self.tasks[task_id] = {
            'id': task_id,
            'conversation_id': conversation_id,
            'task_type': task_type,
            'status': 'pending',
            'payload': payload
        }
        return task_id
    
    def update_task_status(self, task_id, status, result=None):
        if task_id in self.tasks:
            self.tasks[task_id]['status'] = status
            if result:
                self.tasks[task_id]['result'] = result
    
    def save_agent_message(self, from_agent, to_agent, message_type, payload, parent_task_id=None):
        msg_id = len(self.messages)
        self.messages.append({
            'id': msg_id,
            'from_agent': from_agent,
            'to_agent': to_agent,
            'message_type': message_type,
            'payload': payload,
            'parent_task_id': parent_task_id
        })
        return msg_id
    
    def save_audit_log(self, event_type, agent, details):
        self.audit_logs.append({
            'event_type': event_type,
            'agent': agent,
            'details': details
        })


# ========== 测试用例 ==========

def test_mock_redis():
    """测试Redis模拟"""
    redis = MockRedis()
    
    redis.set_task_state('task1', {'status': 'running'})
    assert redis.get_task_state('task1') == {'status': 'running'}
    
    redis.mark_agent_online('search')
    assert redis.get_agent_status('search') == {'status': 'online'}
    
    redis.mark_agent_busy('search', 'task1')
    assert redis.get_agent_status('search') == {'status': 'busy', 'task_id': 'task1'}
    
    print("✅ Redis mock tests passed")


def test_mock_storage():
    """测试存储模拟"""
    storage = MockStorage()
    
    conv_id = storage.create_conversation('Test Chat')
    assert conv_id == 'conv_0'
    
    task_id = storage.create_task(conv_id, 'search', {'query': 'test'})
    assert task_id == 'task_0'
    
    storage.update_task_status(task_id, 'completed', {'results': []})
    assert storage.tasks[task_id]['status'] == 'completed'
    
    storage.save_agent_message('supervisor', 'search', 'task', {'type': 'search'})
    assert len(storage.messages) == 1
    
    print("✅ Storage mock tests passed")


@pytest.mark.asyncio
async def test_search_agent():
    """测试搜索Agent"""
    from src.workers.search_agent import SearchAgent
    
    redis = MockRedis()
    storage = MockStorage()
    
    config = {
        'name': 'search',
        'max_results': 5,
        'system_prompt': 'You are a search agent.'
    }
    
    agent = SearchAgent(config, redis, storage)
    await agent.initialize()
    
    task = {
        'id': 'test_task_1',
        'type': 'search',
        'input': {'query': 'Python programming'}
    }
    
    result = await agent.execute_task(task, {})
    
    assert 'results' in result
    assert result['query'] == 'Python programming'
    assert len(result['results']) > 0
    
    print("✅ Search agent tests passed")


@pytest.mark.asyncio
async def test_code_agent():
    """测试代码Agent"""
    from src.workers.code_agent import CodeAgent
    
    redis = MockRedis()
    storage = MockStorage()
    
    config = {
        'name': 'code',
        'workspace': '/tmp/test_workspace',
        'system_prompt': 'You are a code agent.'
    }
    
    agent = CodeAgent(config, redis, storage)
    await agent.initialize()
    
    # 测试写入文件
    task = {
        'id': 'test_task_2',
        'type': 'code',
        'input': {
            'action': 'write',
            'language': 'python',
            'filename': 'test.py',
            'code': 'print("Hello")'
        }
    }
    
    result = await agent.execute_task(task, {})
    
    assert result['status'] == 'success'
    assert 'path' in result
    
    print("✅ Code agent tests passed")


@pytest.mark.asyncio
async def test_doc_agent():
    """测试文档Agent"""
    from src.workers.doc_agent import DocAgent
    
    redis = MockRedis()
    storage = MockStorage()
    
    config = {
        'name': 'doc',
        'output_dir': '/tmp/test_output',
        'system_prompt': 'You are a doc agent.'
    }
    
    agent = DocAgent(config, redis, storage)
    await agent.initialize()
    
    task = {
        'id': 'test_task_3',
        'type': 'doc',
        'input': {
            'action': 'generate',
            'format': 'markdown',
            'content': '# Test Document\n\nThis is a test.'
        }
    }
    
    result = await agent.execute_task(task, {})
    
    assert result['status'] == 'success'
    assert 'path' in result
    assert 'preview' in result
    
    print("✅ Doc agent tests passed")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 50)
    print("🧪 开始运行测试...")
    print("=" * 50 + "\n")
    
    test_mock_redis()
    test_mock_storage()
    
    # 异步测试需要在事件循环中运行
    asyncio.run(test_search_agent())
    asyncio.run(test_code_agent())
    asyncio.run(test_doc_agent())
    
    print("\n" + "=" * 50)
    print("✅ 所有测试通过!")
    print("=" * 50)


if __name__ == "__main__":
    run_all_tests()
