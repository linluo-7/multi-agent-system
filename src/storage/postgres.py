"""
PostgreSQL Storage Layer
PostgreSQL存储层 - 负责持久化存储
"""

import psycopg2
from psycopg2.extras import RealDictCursor, Json
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import json


class PostgresStorage:
    """PostgreSQL数据库操作类"""
    
    def __init__(self, config: dict):
        self.config = config
        self.conn = None
        self._connect()
    
    def _connect(self):
        """建立数据库连接"""
        try:
            self.conn = psycopg2.connect(
                host=self.config.get('host', 'localhost'),
                port=self.config.get('port', 5432),
                database=self.config.get('name', 'multi_agent_db'),
                user=self.config.get('user', 'postgres'),
                password=self.config.get('password', 'postgres')
            )
            self.conn.autocommit = True
            print(f"[PostgreSQL] Connected to {self.config.get('host')}:{self.config.get('port')}/{self.config.get('name')}")
        except Exception as e:
            print(f"[PostgreSQL] Connection failed: {e}")
            raise
    
    @contextmanager
    def cursor(self):
        """获取数据库游标的上下文管理器"""
        cur = self.conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()
    
    def init_tables(self):
        """初始化数据库表结构"""
        with open('/root/.openclaw/workspace/projects/multi-agent-system/migrations/001_init.sql', 'r') as f:
            sql = f.read()
        
        with self.cursor() as cur:
            cur.execute(sql)
        print("[PostgreSQL] Tables initialized")
    
    # ========== Conversation 操作 ==========
    
    def create_conversation(self, title: Optional[str] = None) -> str:
        """创建新对话"""
        conv_id = str(uuid.uuid4())
        title = title or f"对话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                """,
                (conv_id, title, datetime.now(), datetime.now())
            )
        return conv_id
    
    def get_conversation(self, conv_id: str) -> Optional[Dict]:
        """获取对话信息"""
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM conversations WHERE id = %s",
                (conv_id,)
            )
            return cur.fetchone()
    
    def list_conversations(self, limit: int = 50) -> List[Dict]:
        """获取对话列表"""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM conversations 
                ORDER BY updated_at DESC 
                LIMIT %s
                """,
                (limit,)
            )
            return cur.fetchall()
    
    def update_conversation(self, conv_id: str, **kwargs):
        """更新对话"""
        if not kwargs:
            return
        
        set_clause = ", ".join([f"{k} = %s" for k in kwargs.keys()])
        values = list(kwargs.values()) + [conv_id]
        
        with self.cursor() as cur:
            cur.execute(
                f"UPDATE conversations SET {set_clause}, updated_at = %s WHERE id = %s",
                values + [datetime.now()]
            )
    
    # ========== Task 操作 ==========
    
    def create_task(self, conversation_id: str, task_type: str, payload: dict, task_id: str = None) -> str:
        """创建新任务"""
        # 如果没有提供task_id，则生成一个新的
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        # 验证task_id是有效的UUID格式
        try:
            uuid.UUID(task_id)
        except (ValueError, TypeError):
            task_id = str(uuid.uuid4())
        
        # 如果conversation_id为空，使用系统默认对话ID
        if not conversation_id:
            conversation_id = '00000000-0000-0000-0000-000000000000'
        
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tasks (id, conversation_id, task_type, status, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (task_id, conversation_id, task_type, 'pending', Json(payload), datetime.now(), datetime.now())
            )
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务信息"""
        with self.cursor() as cur:
            cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            return cur.fetchone()
    
    def update_task_status(self, task_id: str, status: str, result: Optional[dict] = None):
        """更新任务状态"""
        with self.cursor() as cur:
            if result is not None:
                cur.execute(
                    """
                    UPDATE tasks 
                    SET status = %s, result = %s, updated_at = %s, completed_at = %s
                    WHERE id = %s
                    """,
                    (status, Json(result), datetime.now(), datetime.now(), task_id)
                )
            else:
                cur.execute(
                    """
                    UPDATE tasks 
                    SET status = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (status, datetime.now(), task_id)
                )
    
    def list_tasks_by_conversation(self, conversation_id: str) -> List[Dict]:
        """获取对话的所有任务"""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM tasks 
                WHERE conversation_id = %s 
                ORDER BY created_at ASC
                """,
                (conversation_id,)
            )
            return cur.fetchall()
    
    # ========== Agent Message 操作 ==========
    
    def save_agent_message(
        self,
        from_agent: str,
        to_agent: str,
        message_type: str,
        payload: dict,
        parent_task_id: Optional[str] = None
    ) -> int:
        """保存Agent间消息"""
        # 验证parent_task_id，如果是无效UUID则设为NULL
        if parent_task_id:
            try:
                uuid.UUID(parent_task_id)
            except (ValueError, TypeError):
                parent_task_id = None  # 无效UUID，设为NULL
        
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_messages 
                (from_agent, to_agent, message_type, payload, parent_task_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (from_agent, to_agent, message_type, Json(payload), parent_task_id, datetime.now())
            )
            return cur.fetchone()['id']
    
    def get_messages_by_task(self, task_id: str) -> List[Dict]:
        """获取任务的所有消息"""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM agent_messages 
                WHERE parent_task_id = %s 
                ORDER BY created_at ASC
                """,
                (task_id,)
            )
            return cur.fetchall()
    
    # ========== Audit Log 操作 ==========
    
    def save_audit_log(self, event_type: str, agent: str, details: dict):
        """保存审计日志"""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (event_type, agent, details, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (event_type, agent, Json(details), datetime.now())
            )
    
    def get_audit_logs(self, agent: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取审计日志"""
        with self.cursor() as cur:
            if agent:
                cur.execute(
                    """
                    SELECT * FROM audit_logs 
                    WHERE agent = %s 
                    ORDER BY created_at DESC 
                    LIMIT %s
                    """,
                    (agent, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM audit_logs 
                    ORDER BY created_at DESC 
                    LIMIT %s
                    """,
                    (limit,)
                )
            return cur.fetchall()
    
    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()
            print("[PostgreSQL] Connection closed")


# 全局实例
_storage_instance: Optional[PostgresStorage] = None


def get_storage(config: dict) -> PostgresStorage:
    """获取或创建存储实例"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = PostgresStorage(config)
    return _storage_instance
