"""
Reasoning Agent
推理校验Agent — 负责逻辑推理、反思纠错、质量评估
"""

import json
import asyncio
from typing import Dict, Any, List, Optional
from .base import BaseWorker


class ReasoningAgent(BaseWorker):
    """推理校验Agent"""

    name = "reasoning"
    description = "推理校验Agent，负责逻辑推理、反思纠错和质量评估"

    def __init__(self, config: dict, redis_manager, postgres_storage, llm_client=None):
        super().__init__(config, redis_manager, postgres_storage)
        self.llm = llm_client

    async def execute(self, task: dict, context: dict) -> dict:
        task_input = task.get('input', {})
        action = task_input.get('action', 'verify')

        if action == 'verify':
            return await self._verify_result(task_input, context)
        elif action == 'evaluate':
            return await self._evaluate_quality(task_input, context)
        elif action == 'reflect':
            return await self._self_reflect(task_input, context)
        elif action == 'correct':
            return await self._suggest_correction(task_input, context)
        else:
            return await self._verify_result(task_input, context)

    async def _verify_result(self, task_input: dict, context: dict) -> dict:
        """校验其他Agent的执行结果"""
        target_result = task_input.get('target_result', {})
        original_task = task_input.get('original_task', {})
        verification_criteria = task_input.get('criteria', [])

        issues = []

        if isinstance(target_result, dict):
            if 'error' in target_result:
                issues.append({
                    'severity': 'error',
                    'type': 'execution_failure',
                    'detail': f"任务执行报错：{target_result['error']}"
                })

            if not target_result:
                issues.append({
                    'severity': 'warning',
                    'type': 'empty_result',
                    'detail': '返回结果为空'
                })

        if self.llm:
            try:
                prompt = self._build_verification_prompt(target_result, original_task)
                llm_response = await self.llm.ainvoke([
                    {"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": prompt}
                ], temperature=0.2)

                for line in llm_response.split('\n'):
                    line = line.strip()
                    if line.startswith('ISSUE:'):
                        issues.append({
                            'severity': 'warning',
                            'type': 'llm_identified',
                            'detail': line.replace('ISSUE:', '').strip()
                        })
            except Exception as e:
                print(f"[ReasoningAgent] LLM verification failed: {e}")

        passed = len([i for i in issues if i['severity'] == 'error']) == 0

        return {
            'passed': passed,
            'issues': issues,
            'issue_count': len(issues),
            'error_count': len([i for i in issues if i['severity'] == 'error']),
            'recommendation': 'retry' if not passed else 'accept',
            'summary': f"校验{'通过' if passed else '未通过'}，发现{len(issues)}个问题"
        }

    async def _evaluate_quality(self, task_input: dict, context: dict) -> dict:
        """评估结果质量"""
        result = task_input.get('result', {})
        expected = task_input.get('expected', {})

        scores = {
            'completeness': self._score_completeness(result),
            'accuracy': self._score_accuracy(result, expected),
            'efficiency': self._score_efficiency(result)
        }

        overall = sum(scores.values()) / len(scores)

        return {
            'scores': scores,
            'overall_score': round(overall, 2),
            'grade': self._grade(overall),
            'passed': overall >= 0.5
        }

    async def _self_reflect(self, task_input: dict, context: dict) -> dict:
        """自我反思：分析执行过程中的问题和改进方向"""
        execution_history = task_input.get('execution_history', [])
        current_plan = task_input.get('plan', [])
        failures = task_input.get('failures', [])

        reflection_points = []

        for failure in failures:
            reflection_points.append({
                'source': 'failure_analysis',
                'observation': f"任务{failure.get('task_id', 'unknown')}失败：{failure.get('error', '')}",
                'suggestion': '建议更换执行策略或简化任务'
            })

        if len(execution_history) > 2:
            similar_failures = sum(
                1 for h in execution_history
                if not h.get('success', True)
            )
            if similar_failures > 1:
                reflection_points.append({
                    'source': 'pattern_recognition',
                    'observation': f'检测到连续{similar_failures}次失败，可能存在系统性问题',
                    'suggestion': '建议人工介入审核或调整模型参数'
                })

        return {
            'reflection_points': reflection_points,
            'improvement_suggestions': [rp['suggestion'] for rp in reflection_points],
            'should_replan': len(reflection_points) > 0
        }

    async def _suggest_correction(self, task_input: dict, context: dict) -> dict:
        """建议修正方案"""
        verification_result = task_input.get('verification_result', {})
        issues = verification_result.get('issues', [])

        corrections = []
        for issue in issues:
            if issue['type'] == 'execution_failure':
                corrections.append({
                    'action': 'retry_with_fallback',
                    'target': issue.get('target_task', ''),
                    'fallback_strategy': '使用简化版本重试'
                })
            elif issue['type'] == 'empty_result':
                corrections.append({
                    'action': 'replan',
                    'target': issue.get('target_task', ''),
                    'fallback_strategy': '调整任务输入重新执行'
                })

        return {
            'corrections': corrections,
            'corrected': len(corrections) > 0,
            'correction_count': len(corrections)
        }

    def _build_verification_prompt(self, result: dict, task: dict) -> str:
        return f"""请校验以下任务执行结果是否符合预期：

原始任务：{json.dumps(task, ensure_ascii=False)[:500]}
执行结果：{json.dumps(result, ensure_ascii=False)[:1000]}

请以 ISSUE: <问题描述> 的格式列出发现的问题。如果没有问题，请回复 "NO_ISSUES"。"""

    def _score_completeness(self, result: dict) -> float:
        if not result:
            return 0.0
        filled_count = sum(1 for v in result.values() if v not in (None, '', [], {}))
        return min(filled_count / max(len(result), 1), 1.0)

    def _score_accuracy(self, result: dict, expected: dict) -> float:
        if not expected:
            return 0.7
        matches = sum(
            1 for k in expected
            if k in result and str(result[k]) == str(expected[k])
        )
        return matches / max(len(expected), 1)

    def _score_efficiency(self, result: dict) -> float:
        execution_time = result.get('execution_time', 30)
        if isinstance(execution_time, (int, float)):
            return max(0.0, min(1.0, 60.0 / max(execution_time, 1.0)))
        return 0.5

    def _grade(self, score: float) -> str:
        if score >= 0.9:
            return 'A'
        elif score >= 0.7:
            return 'B'
        elif score >= 0.5:
            return 'C'
        else:
            return 'D'
