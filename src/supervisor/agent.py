"""
Supervisor Agent (Extended)
总控Agent — 思考-规划-执行-校验-自纠错 全链路推理闭环
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
    RESULT_INTEGRATION_PROMPT,
    ERROR_HANDLING_PROMPT
)


class SupervisorState(dict):
    """Supervisor状态定义"""
    user_input: str
    task_id: str
    conversation_id: str
    plan: List[Dict]
    tasks: Dict[str, Dict]
    results: Dict[str, Any]
    verification_results: Dict[str, Any]
    final_response: str
    errors: List[Dict]
    retry_count: int
    circuit_breaker: bool
    checkpoints: List[Dict]


class SupervisorAgent:
    """总控Agent — 带自纠错回环的完整推理链路"""

    def __init__(
        self,
        config: dict,
        workers: Dict[str, Any],
        redis_manager,
        postgres_storage,
        llm_client=None,
        reasoning_agent=None,
        artifact_store=None
    ):
        self.config = config
        self.workers = workers
        self.redis = redis_manager
        self.storage = postgres_storage
        self.llm = llm_client
        self.reasoning = reasoning_agent
        self.artifact_store = artifact_store

        self.max_retries = config.get('max_retries', 3)
        self.circuit_breaker_threshold = config.get('circuit_breaker_threshold', 5)

        self.graph = self._build_graph()
        self.checkpointer = MemorySaver()

        print(f"[Supervisor] Initialized with {len(workers)} workers + reasoning loop "
              f"(max_retries={self.max_retries})")

    def _build_graph(self) -> StateGraph:
        """构建完整的推理闭环工作流：
        analyze → dispatch → execute → verify → [loop]
                                          ↓
                             integrate ← (passed/retry限)
        """
        workflow = StateGraph(SupervisorState)

        workflow.add_node("analyze", self._analyze_task)
        workflow.add_node("dispatch", self._dispatch_tasks)
        workflow.add_node("execute", self._execute_tasks)
        workflow.add_node("verify", self._verify_results)
        workflow.add_node("correct", self._self_correct)
        workflow.add_node("integrate", self._integrate_results)

        workflow.set_entry_point("analyze")
        workflow.add_edge("analyze", "dispatch")
        workflow.add_edge("dispatch", "execute")
        workflow.add_edge("execute", "verify")

        workflow.add_conditional_edges(
            "verify",
            self._decide_next,
            {
                "integrate": "integrate",
                "correct": "correct",
                "fail": END
            }
        )

        workflow.add_edge("correct", "execute")
        workflow.add_edge("integrate", END)

        return workflow.compile(checkpointer=self.checkpointer)

    async def _analyze_task(self, state: SupervisorState) -> SupervisorState:
        """Phase 1: 思考 — 理解任务并制定计划"""
        user_input = state['user_input']
        task_id = state.get('task_id', 'main')

        self.redis.update_task_state_field(task_id, 'phase', 'analyzing')

        plan = await self._create_plan(user_input)

        self.redis.update_task_state_field(task_id, 'plan', plan)

        checkpoint = {
            'phase': 'analyzed',
            'plan': [{k: v for k, v in p.items() if k != 'agent_instance'} for p in plan],
            'timestamp': datetime.now().isoformat()
        }
        state['checkpoints'] = state.get('checkpoints', []) + [checkpoint]

        return {**state, "plan": plan}

    async def _create_plan(self, user_input: str) -> List[Dict]:
        """使用 LLM 智能规划任务"""
        if self.llm:
            try:
                system_prompt = """你是多Agent协作系统的任务规划专家。

可用Agent:
- search: 网络搜索
- code: 代码编写和执行
- doc: 文档生成和处理
- rag: 知识库文档检索和问答
- reasoning: 逻辑校验和质量评估

输出格式（JSON数组）：
[{"agent": "agent_name", "task_id": "task_0", "task": {"type": "...", "input": {...}}, "depends_on": [], "mode": "parallel"}]"""

                response = await self.llm.ainvoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"用户需求：{user_input}"}
                ], temperature=0.3)

                import re
                json_match = re.search(r'\[.*\]', response, re.DOTALL)
                if json_match:
                    plan = json.loads(json_match.group())
                    print(f"[Supervisor] LLM planned {len(plan)} tasks")
                    return plan
            except Exception as e:
                print(f"[Supervisor] LLM planning failed: {e}")

        return self._create_plan_rule_based(user_input)

    def _create_plan_rule_based(self, user_input: str) -> List[Dict]:
        """基于规则的备用规划器"""
        user_lower = user_input.lower()
        plan = []
        tid = 0

        needs_search = any(kw in user_lower for kw in
            ['搜索', '查找', '查询', '了解', '知道', 'search', 'find', 'look up'])
        needs_code = any(kw in user_lower for kw in
            ['代码', '编程', '写程序', '执行', '运行', 'code', 'program', 'run', 'execute'])
        needs_doc = any(kw in user_lower for kw in
            ['文档', '报告', '生成', '导出', '写文章', 'doc', 'report', 'generate', 'write'])
        needs_rag = any(kw in user_lower for kw in
            ['知识库', '内部文档', '根据文档', '资料库', '合同', '手册',
             'rag', 'knowledge base', 'internal doc', 'reference'])

        if needs_rag:
            plan.append({
                "agent": "rag", "task_id": f"task_{tid}",
                "task": {"type": "rag", "input": {"action": "qa", "query": user_input}},
                "mode": "parallel"
            })
            tid += 1

        if needs_search:
            plan.append({
                "agent": "search", "task_id": f"task_{tid}",
                "task": {"type": "search", "input": {"query": user_input}},
                "mode": "parallel"
            })
            tid += 1

        if needs_code:
            plan.append({
                "agent": "code", "task_id": f"task_{tid}",
                "task": {"type": "code", "input": {"action": "execute", "command": user_input}},
                "depends_on": [], "mode": "parallel"
            })
            tid += 1

        if needs_doc:
            plan.append({
                "agent": "doc", "task_id": f"task_{tid}",
                "task": {"type": "doc", "input": {"action": "generate", "format": "markdown", "content": user_input}},
                "depends_on": [0] if needs_search else [], "mode": "sequential"
            })
            tid += 1

        if not plan:
            plan.append({
                "agent": "search", "task_id": f"task_{tid}",
                "task": {"type": "search", "input": {"query": user_input}},
                "mode": "parallel"
            })

        # 最后追加 reasoning 校验
        plan.append({
            "agent": "reasoning", "task_id": f"task_{tid + 1}",
            "task": {"type": "reasoning", "input": {"action": "verify", "criteria": ["accuracy", "completeness"]}},
            "depends_on": list(range(tid + 1)), "mode": "sequential"
        })

        return plan

    async def _dispatch_tasks(self, state: SupervisorState) -> SupervisorState:
        """Phase 2: 规划 — 分发任务给工作Agent"""
        task_id = state.get('task_id', 'main')
        plan = state['plan']

        self.redis.update_task_state_field(task_id, 'phase', 'dispatching')
        self.redis.set_task_state(task_id, {
            'total_tasks': len(plan),
            'completed_tasks': 0,
            'running_tasks': 0,
            'retry_count': 0
        })

        main_task_id = self.storage.create_task(
            conversation_id=state.get('conversation_id', ''),
            task_type='supervisor',
            payload={'user_input': state.get('user_input', ''), 'plan': plan}
        )

        tasks = {}
        for item in plan:
            agent = item['agent']
            task_def = item['task']

            db_task_id = self.storage.create_task(
                conversation_id=state.get('conversation_id', ''),
                task_type=task_def.get('type', 'unknown'),
                payload=task_def
            )

            tasks[item['task_id']] = {
                'agent': agent,
                'db_task_id': db_task_id,
                'status': 'pending',
                'task_def': task_def,
                'attempts': 0
            }

        return {**state, "tasks": tasks, "main_task_id": main_task_id}

    async def _execute_tasks(self, state: SupervisorState) -> SupervisorState:
        """Phase 3: 执行 — 并行/串行执行任务"""
        task_id = state.get('task_id', 'main')
        plan = state['plan']
        tasks = state['tasks']
        results = state.get('results', {})

        self.redis.update_task_state_field(task_id, 'phase', 'executing')

        context = {
            'blackboard': self.redis.read_from_blackboard(task_id),
            'conversation_id': state.get('conversation_id')
        }

        for item in plan:
            local_task_id = item['task_id']
            agent_name = item['agent']

            if agent_name not in self.workers:
                results[local_task_id] = {'error': f'Agent {agent_name} not found'}
                continue

            if local_task_id in results and 'error' not in results.get(local_task_id, {}):
                continue

            worker = self.workers[agent_name]
            tasks[local_task_id]['attempts'] += 1

            self.redis.update_task_state_field(task_id, f"task_{local_task_id}_status", 'running')
            self.redis.mark_agent_busy(agent_name, local_task_id)

            try:
                result = await worker.execute_task(item['task'], context)
                results[local_task_id] = result
                self.redis.update_task_state_field(task_id, f"task_{local_task_id}_status", 'completed')
                self.storage.update_task_status(
                    tasks[local_task_id]['db_task_id'], 'completed', result
                )
            except Exception as e:
                results[local_task_id] = {'error': str(e)}
                self.redis.update_task_state_field(task_id, f"task_{local_task_id}_status", 'failed')
                self.storage.update_task_status(
                    tasks[local_task_id]['db_task_id'], 'failed', {'error': str(e)}
                )

            self.redis.mark_agent_idle(agent_name)
            context['blackboard'] = self.redis.read_from_blackboard(task_id)

        return {**state, "results": results, "tasks": tasks}

    async def _verify_results(self, state: SupervisorState) -> SupervisorState:
        """Phase 4: 校验 — 验证结果质量"""
        task_id = state.get('task_id', 'main')
        results = state['results']
        plan = state['plan']

        self.redis.update_task_state_field(task_id, 'phase', 'verifying')

        verification_results = {}
        all_passed = True

        for item in plan:
            local_task_id = item['task_id']
            agent_name = item['agent']

            if agent_name == 'reasoning':
                continue

            result = results.get(local_task_id, {})

            if self.reasoning:
                verify_task = {
                    'input': {
                        'action': 'verify',
                        'target_result': result,
                        'original_task': item['task'],
                        'criteria': ['accuracy', 'completeness']
                    }
                }
                context = {'blackboard': self.redis.read_from_blackboard(task_id)}
                try:
                    v_result = await self.reasoning.execute(verify_task, context)
                    verification_results[local_task_id] = v_result
                    if not v_result.get('passed', True):
                        all_passed = False
                except Exception as e:
                    verification_results[local_task_id] = {'passed': True, 'issues': [], 'error': str(e)}
            else:
                local_passed = 'error' not in result
                verification_results[local_task_id] = {
                    'passed': local_passed,
                    'issues': [] if local_passed else [{
                        'severity': 'error',
                        'type': 'execution_failure',
                        'detail': result.get('error', 'Unknown error')
                    }]
                }
                if not local_passed:
                    all_passed = False

        state['retry_count'] = state.get('retry_count', 0)
        if not all_passed:
            state['retry_count'] += 1

        # 熔断检查
        if state['retry_count'] >= self.circuit_breaker_threshold:
            state['circuit_breaker'] = True
            print(f"[Supervisor] Circuit breaker triggered after {state['retry_count']} retries")

        return {**state, "verification_results": verification_results}

    def _decide_next(self, state: SupervisorState) -> str:
        """Phase 5: 决策 — 根据校验结果决定下一步"""
        if state.get('circuit_breaker'):
            return "fail"

        verification_results = state.get('verification_results', {})
        all_passed = all(
            v.get('passed', True) for v in verification_results.values()
            if isinstance(v, dict)
        )

        if all_passed:
            return "integrate"

        retry_count = state.get('retry_count', 0)
        if retry_count < self.max_retries:
            return "correct"

        return "integrate"

    async def _self_correct(self, state: SupervisorState) -> SupervisorState:
        """Phase 6: 自纠错 — 分析失败原因并修正"""
        task_id = state.get('task_id', 'main')
        self.redis.update_task_state_field(task_id, 'phase', 'self_correcting')

        verification_results = state.get('verification_results', {})
        plan = state['plan']
        tasks = state['tasks']

        corrections_applied = []

        for local_task_id, v_result in verification_results.items():
            if v_result.get('passed', True) or not isinstance(v_result, dict):
                continue

            issues = v_result.get('issues', [])
            item = next((p for p in plan if p['task_id'] == local_task_id), None)
            if item is None:
                continue

            for issue in issues:
                if issue.get('severity') == 'error':
                    item['task']['input']['_retry'] = True
                    item['task']['input']['_previous_error'] = issue.get('detail', '')

                    if item['mode'] == 'parallel':
                        item['mode'] = 'sequential'

                    corrections_applied.append({
                        'task_id': local_task_id,
                        'action': 'retry_with_adjustment',
                        'issue': issue.get('detail', '')
                    })

                    if local_task_id in state.get('results', {}):
                        state['results'].pop(local_task_id, None)

                    if local_task_id in tasks:
                        tasks[local_task_id]['status'] = 'pending'

        print(f"[Supervisor] Applied {len(corrections_applied)} corrections")
        return {
            **state,
            "corrections_applied": corrections_applied,
            "tasks": tasks
        }

    async def _integrate_results(self, state: SupervisorState) -> SupervisorState:
        """Phase 7: 整合 — 汇总所有结果生成最终响应"""
        task_id = state.get('task_id', 'main')
        results = state['results']
        user_input = state['user_input']

        self.redis.update_task_state_field(task_id, 'phase', 'integrating')

        final_response = self._build_response(user_input, results)

        self.storage.save_agent_message(
            from_agent='supervisor',
            to_agent='user',
            message_type='final_response',
            payload={'response': final_response},
            parent_task_id=state.get('main_task_id')
        )

        self.redis.update_task_state_field(task_id, 'phase', 'completed')

        # 保存产物版本
        if self.artifact_store:
            self.artifact_store.save_artifact(
                task_id=task_id,
                content=final_response,
                artifact_type='response',
                metadata={
                    'retry_count': state.get('retry_count', 0),
                    'plan_count': len(state.get('plan', [])),
                    'task_count': len(results)
                }
            )

        checkpoint = {
            'phase': 'completed',
            'final_response_preview': final_response[:200],
            'retry_count': state.get('retry_count', 0),
            'circuit_breaker': state.get('circuit_breaker', False),
            'timestamp': datetime.now().isoformat()
        }
        state['checkpoints'] = state.get('checkpoints', []) + [checkpoint]

        return {**state, "final_response": final_response}

    def _build_response(self, user_input: str, results: Dict[str, Any]) -> str:
        """构建最终响应"""
        if not results:
            return "抱歉，我没有找到相关信息。"

        response_parts = []

        for task_id, result in results.items():
            if isinstance(result, dict):
                if 'error' in result:
                    response_parts.append(f"⚠ {task_id}: {result['error']}")
                    continue

                if 'answer' in result:
                    answer = result.get('answer', '')
                    sources = result.get('sources', [])
                    response_parts.append(f"**知识库回答**：\n{answer}")
                    if sources:
                        source_names = [s.get('document', s.get('source', '')) for s in sources[:3]]
                        response_parts.append(f"**参考来源**：{', '.join(source_names)}")
                    needs_fb = result.get('needs_fallback', False)
                    if needs_fb:
                        response_parts.append("⚠ 知识库信息可能不足，建议补充网络搜索")

                elif 'results' in result and result.get('source') != 'rag':
                    items = result.get('results', [])
                    response_parts.append(f"**搜索结果**（{len(items)}条）：")
                    for r in items[:3]:
                        response_parts.append(f"- {r.get('title', '')}: {r.get('snippet', '')[:100]}")

                elif 'context' in result:
                    ctx = result.get('context', '')
                    total = result.get('total_found', 0)
                    response_parts.append(f"**RAG检索结果**（{total}条匹配）：\n{ctx[:500]}")

                elif 'stdout' in result:
                    response_parts.append(f"**代码执行结果**：\n```\n{result.get('stdout', '')[:500]}\n```")

                elif 'path' in result:
                    response_parts.append(f"**文档已生成**：{result.get('filename', 'unknown')}")

                elif 'passed' in result:
                    status = "通过" if result['passed'] else "未通过"
                    response_parts.append(f"**校验{status}** — 发现问题{result.get('issue_count', 0)}个")

                elif 'corrections' in result:
                    response_parts.append(f"**自纠错建议**：{len(result.get('corrections', []))}条修正方案")

        if response_parts:
            return '\n\n'.join(response_parts)
        return "任务已完成，但没有返回具体结果。"

    # ======== 断点续跑 ========

    async def process(
        self,
        user_input: str,
        conversation_id: str,
        task_id: str,
        resume_from_checkpoint: str = None
    ) -> str:
        """处理用户输入，支持断点续跑"""
        initial_state = {
            'user_input': user_input,
            'conversation_id': conversation_id,
            'task_id': task_id,
            'plan': [],
            'tasks': {},
            'results': {},
            'verification_results': {},
            'final_response': '',
            'errors': [],
            'retry_count': 0,
            'circuit_breaker': False,
            'checkpoints': []
        }

        config = {"configurable": {"thread_id": task_id}}
        if resume_from_checkpoint:
            config["configurable"]["checkpoint_id"] = resume_from_checkpoint

        try:
            final_state = None
            async for state in self.graph.astream(initial_state, config):
                final_state = state

            response = final_state.get('final_response', '处理完成') if final_state else '处理失败'
        except Exception as e:
            response = f"系统处理异常：{str(e)}"
            print(f"[Supervisor] Process error: {e}")

        return response

    async def get_checkpoints(self, task_id: str) -> List[Dict]:
        """获取任务的所有检查点（用于断点恢复）"""
        config = {"configurable": {"thread_id": task_id}}
        checkpoints = []
        async for chk in self.checkpointer.alist(config):
            checkpoints.append({
                'checkpoint_id': chk.get('configurable', {}).get('checkpoint_id'),
                'timestamp': chk.get('timestamp')
            })
        return checkpoints

    async def resume_task(self, task_id: str, checkpoint_id: str) -> str:
        """从断点恢复任务"""
        print(f"[Supervisor] Resuming task {task_id} from checkpoint {checkpoint_id}")
        return await self.process("", "", task_id, resume_from_checkpoint=checkpoint_id)
