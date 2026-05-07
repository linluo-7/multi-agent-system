"""
Skill Manager
技能自进化管理器 — 自动识别高频任务、封装Skill、迭代优化、冗余淘汰
"""

import json
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict


class SkillManager:
    """Agent技能自进化管理器"""

    def __init__(self, config: dict, memory_manager, postgres_storage, redis_manager):
        self.config = config
        self.memory = memory_manager
        self.storage = postgres_storage
        self.redis = redis_manager

        self.skill_threshold = config.get('memory', {}).get('skill_threshold', 3)
        self.eval_threshold = config.get('memory', {}).get('eval_threshold', 0.6)
        self.max_skills = config.get('memory', {}).get('max_skills', 100)

        self._task_patterns = defaultdict(list)
        self._initialized = False

    async def initialize(self):
        self._initialized = True
        print(f"[SkillManager] Initialized (threshold={self.skill_threshold}, eval_threshold={self.eval_threshold})")

    async def record_task_execution(
        self,
        task_type: str,
        agent_name: str,
        task_input: dict,
        task_result: dict,
        execution_time: float,
        success: bool
    ):
        """记录任务执行，用于模式分析和技能发现"""
        pattern_key = f"{agent_name}:{task_type}"

        execution_record = {
            'input_signature': self._compute_input_signature(task_input),
            'input_template': task_input,
            'result_template': self._extract_result_structure(task_result),
            'success': success,
            'execution_time': execution_time,
            'timestamp': datetime.now().isoformat()
        }

        self._task_patterns[pattern_key].append(execution_record)

        # 只保留最近N条记录
        if len(self._task_patterns[pattern_key]) > 50:
            self._task_patterns[pattern_key] = self._task_patterns[pattern_key][-50:]

        await self._check_skill_emergence(pattern_key)

    async def _check_skill_emergence(self, pattern_key: str):
        """检测高频任务模式，判断是否应自动生成Skill"""
        records = self._task_patterns.get(pattern_key, [])
        if len(records) < self.skill_threshold:
            return

        recent_successes = [r for r in records[-10:] if r['success']]
        success_rate = len(recent_successes) / max(len(records[-10:]), 1)

        if success_rate < self.eval_threshold:
            return

        agent_name, task_type = pattern_key.split(':', 1)

        existing = await self.memory.get_skill_templates(
            task_type=task_type,
            min_success_rate=self.eval_threshold
        )

        similar = [
            s for s in existing
            if s['name'] == pattern_key
        ]

        recent_inputs = [r['input_template'] for r in records[-5:] if r['success']]

        if similar:
            skill = similar[0]
            print(f"[SkillManager] Skill '{pattern_key}' already exists, updating from {len(records)} executions")
            await self._update_skill_from_patterns(skill['id'], recent_inputs, success_rate)
        else:
            skill_id = await self._create_skill_from_patterns(
                pattern_key, agent_name, task_type,
                recent_inputs, records[-10:], success_rate
            )
            print(f"[SkillManager] Auto-generated skill '{pattern_key}' (id={skill_id[:8]}...) "
                  f"from {len(records)} executions, success_rate={success_rate:.2f}")

    async def _create_skill_from_patterns(
        self,
        pattern_key: str,
        agent_name: str,
        task_type: str,
        recent_inputs: List[dict],
        records: List[dict],
        success_rate: float
    ) -> str:
        """从任务模式自动创建Skill模板"""
        merged_input = self._merge_input_patterns(recent_inputs)

        prompt_template = self._generate_prompt_template(agent_name, task_type, merged_input)

        tool_sequence = self._infer_tool_sequence(records)

        skill_id = await self.memory.save_skill_template(
            name=pattern_key,
            task_type=task_type,
            description=f"自动生成的{agent_name}技能：{task_type}（成功率{success_rate:.1%}）",
            prompt_template=prompt_template,
            tool_sequence=tool_sequence,
            input_schema=self._infer_input_schema(merged_input),
            success_rate=success_rate
        )

        return skill_id

    async def _update_skill_from_patterns(
        self,
        skill_id: str,
        recent_inputs: List[dict],
        success_rate: float
    ):
        """基于最新执行更新已有Skill"""
        with self.storage.cursor() as cur:
            cur.execute(
                """
                UPDATE skill_templates
                SET success_rate = %s, updated_at = %s
                WHERE id = %s
                """,
                (success_rate, datetime.now(), skill_id)
            )

    async def evaluate_skill(self, skill_id: str, task_id: str, passed: bool, score: float, feedback: str = ""):
        """评估技能执行效果"""
        eval_id = str(uuid.uuid4())

        with self.storage.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skill_evaluations
                (id, skill_id, task_id, passed, score, feedback, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (eval_id, skill_id, task_id, passed, score, feedback, datetime.now())
            )

        await self.memory.update_skill_success_rate(skill_id)
        await self._prune_low_performance_skills()

    async def _prune_low_performance_skills(self):
        """淘汰低效技能"""
        with self.storage.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, success_rate, usage_count
                FROM skill_templates
                WHERE usage_count >= %s AND success_rate < %s
                ORDER BY success_rate ASC
                """,
                (self.skill_threshold, self.eval_threshold)
            )
            candidates = cur.fetchall()

            for skill in candidates:
                days_since_update = 30
                cur.execute(
                    """
                    SELECT MAX(created_at) as last_eval FROM skill_evaluations
                    WHERE skill_id = %s
                    """,
                    (skill['id'],)
                )
                row = cur.fetchone()
                if row and row['last_eval']:
                    days_since_update = (datetime.now() - row['last_eval']).days

                if days_since_update > 7 and skill['usage_count'] >= self.skill_threshold:
                    cur.execute(
                        "UPDATE skill_templates SET success_rate = 0.0, "
                        "description = description || ' [已淘汰]' WHERE id = %s",
                        (skill['id'],)
                    )
                    print(f"[SkillManager] Pruned low-performance skill: {skill['name']} "
                          f"(rate={skill['success_rate']:.2f}, usage={skill['usage_count']})")

    async def get_matching_skills(self, task_type: str, task_input: dict) -> List[dict]:
        """获取匹配的技能模板"""
        skills = await self.memory.get_skill_templates(
            task_type=task_type,
            min_success_rate=self.eval_threshold
        )

        matched = []
        for skill in skills:
            schema = skill.get('input_schema', {})
            if isinstance(schema, str):
                try:
                    schema = json.loads(schema)
                except json.JSONDecodeError:
                    schema = {}

            match_score = self._compute_schema_match(schema, task_input)
            if match_score > 0.5:
                matched.append({**skill, 'match_score': match_score})

        matched.sort(key=lambda x: x['match_score'], reverse=True)
        return matched[:5]

    def get_skill_stats(self) -> dict:
        """获取技能系统统计"""
        with self.storage.cursor() as cur:
            cur.execute("SELECT COUNT(*) as total FROM skill_templates")
            total = cur.fetchone()['total']

            cur.execute(
                "SELECT COUNT(*) as active FROM skill_templates WHERE success_rate >= %s",
                (self.eval_threshold,)
            )
            active = cur.fetchone()['active']

            cur.execute("SELECT COUNT(*) as evals FROM skill_evaluations")
            evals = cur.fetchone()['evals']

        return {
            'total_skills': total,
            'active_skills': active,
            'pruned_skills': total - active,
            'total_evaluations': evals,
            'auto_generated': len([
                k for k in self._task_patterns
                if len(self._task_patterns[k]) >= self.skill_threshold
            ])
        }

    # ======== 辅助方法 ========

    def _compute_input_signature(self, task_input: dict) -> str:
        """计算输入特征签名"""
        if not task_input:
            return "empty"
        return str(sorted(task_input.keys()))

    def _extract_result_structure(self, result: dict) -> dict:
        """提取结果结构模板"""
        if not result:
            return {}
        return {k: type(v).__name__ for k, v in result.items()}

    def _merge_input_patterns(self, inputs: List[dict]) -> dict:
        """合并多个输入模式"""
        merged = {}
        for inp in inputs:
            for key, value in inp.items():
                if key not in merged:
                    merged[key] = value
        return merged

    def _generate_prompt_template(self, agent_name: str, task_type: str, input_pattern: dict) -> str:
        """生成Prompt模板"""
        input_desc = '\n'.join([f"  - {k}: <{k}>" for k in input_pattern.keys()])
        return f"""执行{agent_name}的{task_type}任务：

输入参数：
{input_desc or '  （无固定参数）'}

按照以下步骤执行：
1. 解析输入参数
2. 调用所需工具
3. 返回结构化结果"""

    def _infer_tool_sequence(self, records: List[dict]) -> List[str]:
        """推断工具调用序列"""
        tools = set()
        for r in records:
            if r['success']:
                result = r.get('result_template', {})
                if 'tools_used' in result:
                    tools.update(result['tools_used'])
        return list(tools) if tools else ['default_tool']

    def _infer_input_schema(self, input_pattern: dict) -> dict:
        """推断输入Schema"""
        schema = {}
        for key, value in input_pattern.items():
            schema[key] = {
                'type': type(value).__name__,
                'required': True,
                'example': str(value)[:100]
            }
        return schema

    def _compute_schema_match(self, schema: dict, task_input: dict) -> float:
        """计算输入与技能模板的匹配度"""
        if not schema or not task_input:
            return 0.3

        required = [k for k, v in schema.items() if v.get('required', False)]
        if not required:
            return 0.3

        matched = sum(1 for k in required if k in task_input)
        return matched / len(required)
