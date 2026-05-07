"""
Memory Manager (Hermes Architecture)
三层分层记忆管理器 — 会话记忆 / 技能记忆 / 长期记忆

参考 Hermes 分层记忆架构设计：
- 会话记忆 (Session): Redis — 临时上下文与任务状态
- 技能记忆 (Skill): PostgreSQL — 标准化工具调用、问答模板
- 长期记忆 (Long-term): Milvus(向量) + Neo4j(图谱) — 全局知识与历史经验
"""

import json
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta


class MemoryManager:
    """三层分层记忆管理器"""

    def __init__(
        self,
        config: dict,
        redis_manager,
        postgres_storage,
        milvus_manager=None,
        neo4j_manager=None,
        embedding_service=None
    ):
        self.config = config
        self.redis = redis_manager
        self.storage = postgres_storage
        self.milvus = milvus_manager
        self.neo4j = neo4j_manager
        self.embedding = embedding_service

        self.session_ttl = config.get('memory', {}).get('session_ttl', 3600)
        self.key_prefix = config.get('storage', {}).get('key_prefix', 'mas')

    # =================================================================
    # 第一层：会话记忆（Session Memory）— Redis
    # =================================================================

    async def save_session_context(self, session_id: str, context: dict):
        """保存会话上下文"""
        key = f"{self.key_prefix}:session:{session_id}"
        self.redis.client.hset(key, mapping={
            k: json.dumps(v) for k, v in context.items()
        })
        self.redis.client.expire(key, self.session_ttl)

    async def get_session_context(self, session_id: str) -> dict:
        """获取会话上下文"""
        key = f"{self.key_prefix}:session:{session_id}"
        data = self.redis.client.hgetall(key)
        if not data:
            return {}
        return {k: json.loads(v) for k, v in data.items()}

    async def append_conversation_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict = None
    ):
        """追加对话轮次"""
        key = f"{self.key_prefix}:session:{session_id}:history"
        turn = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        self.redis.client.rpush(key, json.dumps(turn))
        self.redis.client.expire(key, self.session_ttl)

        max_history = self.config.get('storage', {}).get('max_history', 50)
        current_len = self.redis.client.llen(key)
        if current_len > max_history:
            self.redis.client.ltrim(key, current_len - max_history, -1)

    async def get_conversation_history(self, session_id: str, limit: int = 10) -> List[dict]:
        """获取对话历史"""
        key = f"{self.key_prefix}:session:{session_id}:history"
        items = self.redis.client.lrange(key, -limit, -1)
        return [json.loads(item) for item in items]

    async def summarize_session(self, session_id: str) -> str:
        """生成会话摘要（写入长期记忆）"""
        history = await self.get_conversation_history(session_id, limit=20)
        if not history:
            return ""

        summary_parts = []
        topics = set()
        for turn in history:
            content = turn.get('content', '')
            if len(content) > 100:
                summary_parts.append(f"[{turn['role']}]: {content[:100]}...")
            else:
                summary_parts.append(f"[{turn['role']}]: {content}")

            if turn.get('metadata', {}).get('topic'):
                topics.add(turn['metadata']['topic'])

        summary = f"会话摘要 (共{len(history)}轮)\n" + '\n'.join(summary_parts[-5:])
        if topics:
            summary = f"涉及主题: {', '.join(topics)}\n{summary}"

        return summary

    # =================================================================
    # 第二层：技能记忆（Skill Memory）— PostgreSQL
    # =================================================================

    async def save_skill_template(
        self,
        name: str,
        task_type: str,
        description: str,
        prompt_template: str,
        tool_sequence: List[str],
        input_schema: dict = None,
        success_rate: float = 0.0
    ) -> str:
        """保存可复用技能模板"""
        skill_id = str(uuid.uuid4())

        with self.storage.cursor() as cur:
            cur.execute(
                """
                INSERT INTO skill_templates
                (id, name, task_type, description, prompt_template, tool_sequence,
                 input_schema, success_rate, usage_count, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s)
                RETURNING id
                """,
                (
                    skill_id, name, task_type, description,
                    prompt_template, json.dumps(tool_sequence),
                    json.dumps(input_schema or {}),
                    success_rate, datetime.now(), datetime.now()
                )
            )
            return cur.fetchone()['id']

    async def get_skill_templates(
        self,
        task_type: str = None,
        min_success_rate: float = 0.0
    ) -> List[dict]:
        """获取技能模板"""
        with self.storage.cursor() as cur:
            if task_type:
                cur.execute(
                    """
                    SELECT * FROM skill_templates
                    WHERE task_type = %s AND success_rate >= %s
                    ORDER BY usage_count DESC, success_rate DESC
                    LIMIT 20
                    """,
                    (task_type, min_success_rate)
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM skill_templates
                    WHERE success_rate >= %s
                    ORDER BY usage_count DESC, success_rate DESC
                    LIMIT 20
                    """,
                    (min_success_rate,)
                )
            return cur.fetchall()

    async def record_skill_usage(self, skill_id: str, success: bool):
        """记录技能使用情况"""
        with self.storage.cursor() as cur:
            cur.execute(
                """
                UPDATE skill_templates
                SET usage_count = usage_count + 1,
                    updated_at = %s
                WHERE id = %s
                """,
                (datetime.now(), skill_id)
            )

    async def update_skill_success_rate(self, skill_id: str):
        """更新技能成功率（基于评估记录）"""
        with self.storage.cursor() as cur:
            cur.execute(
                """
                SELECT AVG(CASE WHEN passed THEN 1.0 ELSE 0.0 END) as rate
                FROM skill_evaluations WHERE skill_id = %s
                """,
                (skill_id,)
            )
            row = cur.fetchone()
            if row and row['rate'] is not None:
                cur.execute(
                    "UPDATE skill_templates SET success_rate = %s, updated_at = %s WHERE id = %s",
                    (float(row['rate']), datetime.now(), skill_id)
                )

    # =================================================================
    # 第三层：长期记忆（Long-term Memory）— Milvus + Neo4j
    # =================================================================

    async def store_long_term_memory(
        self,
        content: str,
        memory_type: str,
        metadata: dict = None,
        entities: List[dict] = None,
        relations: List[dict] = None
    ) -> str:
        """存储长期记忆（向量 + 图谱）"""
        memory_id = str(uuid.uuid4())
        metadata = metadata or {}

        if self.embedding and self.milvus:
            embedding = await self.embedding.encode_single(content)
            await self.milvus.insert('multi_agent_memory', [{
                'id': memory_id,
                'text': content,
                'embedding': embedding,
                'metadata': {
                    'memory_type': memory_type,
                    **metadata
                },
                'timestamp': datetime.now().timestamp()
            }])

        if self.neo4j:
            await self.neo4j.create_entity('Memory', {
                'id': memory_id,
                'type': memory_type,
                'content': content[:500],
                'metadata': json.dumps(metadata)
            })

            if entities:
                for entity in entities:
                    entity.setdefault('source_memory', memory_id)
                    await self.neo4j.create_entity(entity.get('label', 'Entity'), entity)

            if relations:
                for rel in relations:
                    await self.neo4j.create_relation(
                        rel['from'], rel['to'],
                        rel.get('type', 'RELATED_TO')
                    )

        return memory_id

    async def recall_long_term_memory(
        self,
        query: str,
        memory_type: str = None,
        top_k: int = 10
    ) -> List[dict]:
        """检索长期记忆"""
        results = []

        if self.embedding and self.milvus:
            query_vec = await self.embedding.encode_single(query)
            filter_expr = f"memory_type == '{memory_type}'" if memory_type else None
            vector_results = await self.milvus.search(
                'multi_agent_memory', query_vec,
                top_k=top_k, filter_expr=filter_expr
            )
            results.extend(vector_results)

        if self.neo4j:
            graph_results = await self.neo4j.search_by_keyword(
                query, labels=['Memory', 'Entity'], limit=top_k
            )
            for gr in graph_results:
                results.append({
                    'id': gr.get('id', ''),
                    'text': gr.get('content', gr.get('name', '')),
                    'score': 0.7,
                    'source': 'knowledge_graph',
                    'metadata': {'entity_label': gr.get('label', '')}
                })

        results.sort(key=lambda x: x.get('score', 0.0), reverse=True)
        return results[:top_k]

    async def forget_memory(self, memory_id: str):
        """遗忘长期记忆"""
        if self.milvus:
            await self.milvus.delete_by_ids('multi_agent_memory', [memory_id])

    # =================================================================
    # 记忆整合
    # =================================================================

    async def extract_session_insights(self, session_id: str) -> dict:
        """从会话中萃取可沉淀的长期记忆"""
        summary = await self.summarize_session(session_id)
        history = await self.get_conversation_history(session_id, limit=50)

        return {
            'summary': summary,
            'total_turns': len(history),
            'topics': list(set(
                t.get('metadata', {}).get('topic', '')
                for t in history
                if t.get('metadata', {}).get('topic')
            )),
            'agent_interactions': {
                agent: sum(
                    1 for t in history
                    if t.get('metadata', {}).get('agent') == agent
                )
                for agent in ['search', 'code', 'doc', 'reasoning']
            }
        }

    async def consolidate_memories(self, session_id: str):
        """记忆整合：将会话精华沉淀到长期记忆"""
        insights = await self.extract_session_insights(session_id)
        if insights['summary']:
            await self.store_long_term_memory(
                content=insights['summary'],
                memory_type='session_insight',
                metadata={
                    'session_id': session_id,
                    'topics': insights['topics'],
                    'agent_interactions': insights['agent_interactions']
                }
            )
        print(f"[MemoryManager] Session '{session_id}' consolidated to long-term memory")
