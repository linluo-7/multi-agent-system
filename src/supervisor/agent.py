"""
Supervisor Agent
总控Agent - 负责任务调度和Agent协作编排
"""

import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .prompts import (
    SUPERVISOR_SYSTEM_PROMPT,
    TASK_ANALYSIS_PROMPT,
    RESULT_INTEGRATION_PROMPT
)


class SupervisorState(dict):
    """Supervisor状态定义"""
    user_input: str
    plan: List[Dict]
    tasks: Dict[str, Dict]
    results: Dict[str, Any]
    final_response: str
    errors: List[Dict]


class SupervisorAgent:
    """总控Agent"""
    
    def __init__(self, config: dict, workers: Dict[str, Any], redis_manager, postgres_storage):
        self.config = config
        self.workers = workers  # name -> worker instance
        self.redis = redis_manager
        self.storage = postgres_storage
        
        # 构建LangGraph工作流
        self.graph = self._build_graph()
        
        print(f"[Supervisor] Initialized with {len(workers)} workers: {list(workers.keys())}")
    
    def _build_graph(self) -> StateGraph:
        """构建LangGraph工作流"""
        workflow = StateGraph(SupervisorState)
        
        # 添加节点
        workflow.add_node("analyze", self._analyze_task)
        workflow.add_node("dispatch", self._dispatch_tasks)
        workflow.add_node("monitor", self._monitor_progress)
        workflow.add_node("integrate", self._integrate_results)
        
        # 设置边
        workflow.set_entry_point("analyze")
        workflow.add_edge("analyze", "dispatch")
        workflow.add_edge("dispatch", "monitor")
        workflow.add_edge("monitor", "integrate")
        workflow.add_edge("integrate", END)
        
        # 编译
        return workflow.compile(checkpointer=MemorySaver())
    
    async def _analyze_task(self, state: SupervisorState) -> SupervisorState:
        """分析用户需求，制定执行计划"""
        user_input = state['user_input']
        
        # 更新Redis状态
        self.redis.update_task_state_field(
            state.get('task_id', 'main'),
            'phase',
            'analyzing'
        )
        
        # 使用LLM分析任务（这里用简单的规则匹配作为演示）
        plan = await self._create_plan(user_input)
        
        # 保存计划到PostgreSQL
        task_id = state.get('task_id')
        if task_id:
            self.storage.save_agent_message(
                from_agent='supervisor',
                to_agent='system',
                message_type='plan',
                payload={'plan': plan},
                parent_task_id=task_id
            )
        
        return {**state, "plan": plan}
    
    async def _create_plan(self, user_input: str) -> List[Dict]:
        """创建执行计划"""
        # 简单的规则匹配演示
        # 生产环境中，这里应该调用LLM进行更智能的规划
        
        user_lower = user_input.lower()
        plan = []
        
        # 检测需要哪些Agent
        needs_search = any(kw in user_lower for kw in ['搜索', '查找', '查询', '了解', '知道', 'search', 'find', 'look up'])
        needs_code = any(kw in user_lower for kw in ['代码', '编程', '写程序', '执行', '运行', 'code', 'program', 'run', 'execute'])
        needs_doc = any(kw in user_lower for kw in ['文档', '报告', '生成', '导出', '写文章', 'doc', 'report', 'generate', 'write'])
        
        task_id_counter = 0
        
        if needs_search:
            plan.append({
                "agent": "search",
                "task_id": f"task_{task_id_counter}",
                "task": {
                    "type": "search",
                    "input": {"query": user_input}
                },
                "mode": "parallel"
            })
            task_id_counter += 1
        
        if needs_code:
            plan.append({
                "agent": "code",
                "task_id": f"task_{task_id_counter}",
                "task": {
                    "type": "code",
                    "input": {"action": "execute", "command": self._extract_code_command(user_input)}
                },
                "depends_on": [],
                "mode": "parallel"
            })
            task_id_counter += 1
        
        if needs_doc:
            # doc任务通常依赖search结果
            depends = []
            if needs_search:
                depends = [0]
            
            plan.append({
                "agent": "doc",
                "task_id": f"task_{task_id_counter}",
                "task": {
                    "type": "doc",
                    "input": {
                        "action": "generate",
                        "format": "markdown",
                        "content": user_input
                    }
                },
                "depends_on": depends,
                "mode": "sequential"
            })
            task_id_counter += 1
        
        # 如果没有匹配任何Agent，生成一个默认的search任务
        if not plan:
            plan.append({
                "agent": "search",
                "task_id": f"task_{task_id_counter}",
                "task": {
                    "type": "search",
                    "input": {"query": user_input}
                },
                "mode": "parallel"
            })
        
        return plan
    
    def _extract_code_command(self, text: str) -> Optional[str]:
        """从文本中提取代码执行命令"""
        # 简单实现，查找反引号中的内容
        import re
        matches = re.findall(r'`([^`]+)`', text)
        if matches:
            return matches[0]
        return None
    
    async def _dispatch_tasks(self, state: SupervisorState) -> SupervisorState:
        """分发任务给各Agent"""
        task_id = state.get('task_id', 'main')
        plan = state['plan']
        
        self.redis.update_task_state_field(task_id, 'phase', 'dispatching')
        self.redis.set_task_state(task_id, {
            'total_tasks': len(plan),
            'completed_tasks': 0,
            'running_tasks': 0
        })
        
        # 创建任务记录到PostgreSQL
        tasks = {}
        for item in plan:
            agent = item['agent']
            task_def = item['task']
            
            # 创建任务记录
            db_task_id = self.storage.create_task(
                conversation_id=state.get('conversation_id', ''),
                task_type=task_def.get('type', 'unknown'),
                payload=task_def
            )
            
            tasks[item['task_id']] = {
                'agent': agent,
                'db_task_id': db_task_id,
                'status': 'pending',
                'task_def': task_def
            }
            
            # 更新Redis
            self.redis.set_task_state(task_id, {
                f"task_{item['task_id']}_status": 'pending'
            })
        
        return {**state, "tasks": tasks}
    
    async def _monitor_progress(self, state: SupervisorState) -> SupervisorState:
        """监控任务执行进度"""
        task_id = state.get('task_id', 'main')
        plan = state['plan']
        tasks = state['tasks']
        results = {}
        
        # 并行执行所有可以并行的任务
        async def execute_task(item: Dict, context: Dict):
            task_def = item['task']
            agent_name = item['agent']
            local_task_id = item['task_id']
            
            if agent_name not in self.workers:
                return local_task_id, {'error': f'Agent {agent_name} not found'}
            
            worker = self.workers[agent_name]
            
            # 更新状态为running
            self.redis.update_task_state_field(task_id, f"task_{local_task_id}_status", 'running')
            self.redis.mark_agent_busy(agent_name, local_task_id)
            
            try:
                result = await worker.execute_task(task_def, context)
                self.redis.update_task_state_field(task_id, f"task_{local_task_id}_status", 'completed')
                self.storage.update_task_status(tasks[local_task_id]['db_task_id'], 'completed', result)
                return local_task_id, result
            except Exception as e:
                error_result = {'error': str(e)}
                self.redis.update_task_state_field(task_id, f"task_{local_task_id}_status", 'failed')
                self.storage.update_task_status(tasks[local_task_id]['db_task_id'], 'failed', error_result)
                return local_task_id, error_result
        
        # 构建上下文（从Redis读取黑板数据）
        context = {
            'blackboard': self.redis.read_from_blackboard(task_id),
            'conversation_id': state.get('conversation_id')
        }
        
        # 分析依赖关系，分批执行
        executed = set()
        
        for item in plan:
            depends = item.get('depends_on', [])
            
            # 等待依赖完成
            if depends:
                await self._wait_for_dependencies(depends, results, task_id)
            
            # 执行当前任务
            local_id, result = await execute_task(item, context)
            results[local_id] = result
            executed.add(local_id)
            
            # 更新上下文（加入新的黑板数据）
            context['blackboard'] = self.redis.read_from_blackboard(task_id)
        
        return {**state, "results": results}
    
    async def _wait_for_dependencies(self, depends: List[int], results: Dict, task_id: str, timeout: int = 30):
        """等待依赖任务完成"""
        start = datetime.now()
        while True:
            all_done = all(str(i) in results for i in depends)
            if all_done:
                break
            
            if (datetime.now() - start).seconds > timeout:
                raise TimeoutError(f"Dependencies not satisfied after {timeout}s")
            
            await asyncio.sleep(0.1)
    
    async def _integrate_results(self, state: SupervisorState) -> SupervisorState:
        """整合各Agent的执行结果"""
        task_id = state.get('task_id', 'main')
        results = state['results']
        user_input = state['user_input']
        
        self.redis.update_task_state_field(task_id, 'phase', 'integrating')
        
        # 构建最终响应
        final_response = self._build_response(user_input, results)
        
        # 保存最终结果
        self.storage.save_agent_message(
            from_agent='supervisor',
            to_agent='user',
            message_type='final_response',
            payload={'response': final_response},
            parent_task_id=task_id
        )
        
        # 更新任务状态
        self.redis.update_task_state_field(task_id, 'phase', 'completed')
        
        return {**state, "final_response": final_response}
    
    def _build_response(self, user_input: str, results: Dict[str, Any]) -> str:
        """构建最终响应"""
        if not results:
            return "抱歉，我没有找到相关信息。"
        
        response_parts = []
        
        # 整理各Agent的结果
        for task_id, result in results.items():
            if isinstance(result, dict):
                if 'error' in result:
                    continue
                
                # search结果
                if 'results' in result:
                    response_parts.append(f"📚 搜索结果（共{len(result.get('results', []))}条）：\n")
                    for r in result.get('results', [])[:3]:
                        title = r.get('title', '无标题')
                        snippet = r.get('snippet', '')
                        response_parts.append(f"• **{title}**：{snippet}\n")
                
                # code结果
                elif 'stdout' in result:
                    response_parts.append(f"💻 代码执行结果：\n{result.get('stdout', '')}\n")
                
                # doc结果
                elif 'path' in result:
                    response_parts.append(f"📄 文档已生成：{result.get('filename', 'unknown')}\n")
                    if 'preview' in result:
                        response_parts.append(f"预览：{result.get('preview', '')[:200]}...\n")
        
        if response_parts:
            return '\n'.join(response_parts)
        else:
            return "任务已完成，但没有返回具体结果。"
    
    async def process(self, user_input: str, conversation_id: str, task_id: str) -> str:
        """
        处理用户输入
        
        Args:
            user_input: 用户输入
            conversation_id: 对话ID
            task_id: 任务ID
        
        Returns:
            最终响应
        """
        initial_state = {
            'user_input': user_input,
            'conversation_id': conversation_id,
            'task_id': task_id,
            'plan': [],
            'tasks': {},
            'results': {},
            'final_response': '',
            'errors': []
        }
        
        # 执行工作流
        final_state = None
        async for state in self.graph.astream(initial_state):
            final_state = state
        
        return final_state.get('final_response', '处理完成') if final_state else '处理失败'
