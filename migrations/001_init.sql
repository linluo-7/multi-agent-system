-- Multi-Agent System Database Schema
-- 多Agent协作系统数据库表结构
-- Version: 1.0.0
-- Created: 2026-04-03

-- 启用UUID扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 表1: conversations - 对话记录表
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

COMMENT ON TABLE conversations IS '对话记录表，存储用户与系统的每次对话会话';
COMMENT ON COLUMN conversations.id IS '对话唯一标识符';
COMMENT ON COLUMN conversations.title IS '对话标题';
COMMENT ON COLUMN conversations.created_at IS '对话创建时间';
COMMENT ON COLUMN conversations.updated_at IS '对话最后更新时间';
COMMENT ON COLUMN conversations.metadata IS '扩展元数据';

-- 对话更新时间自动更新触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 表2: tasks - 任务记录表
-- ============================================
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    payload JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

COMMENT ON TABLE tasks IS '任务记录表，存储每个执行的任务详情';
COMMENT ON COLUMN tasks.conversation_id IS '所属对话ID';
COMMENT ON COLUMN tasks.task_type IS '任务类型：search/code/doc等';
COMMENT ON COLUMN tasks.status IS '任务状态：pending/running/completed/failed';
COMMENT ON COLUMN tasks.payload IS '任务输入参数';
COMMENT ON COLUMN tasks.result IS '任务执行结果';
COMMENT ON COLUMN tasks.error_message IS '错误信息';
COMMENT ON COLUMN tasks.started_at IS '任务开始时间';
COMMENT ON COLUMN tasks.completed_at IS '任务完成时间';

-- 任务状态更新触发器
CREATE TRIGGER update_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 表3: agent_messages - Agent间消息表
-- ============================================
CREATE TABLE IF NOT EXISTS agent_messages (
    id SERIAL PRIMARY KEY,
    from_agent VARCHAR(50) NOT NULL,
    to_agent VARCHAR(50) NOT NULL,
    message_type VARCHAR(20) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    parent_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE agent_messages IS 'Agent间消息表，记录各Agent之间的通信';
COMMENT ON COLUMN agent_messages.from_agent IS '消息发送方Agent名称';
COMMENT ON COLUMN agent_messages.to_agent IS '消息接收方Agent名称';
COMMENT ON COLUMN agent_messages.message_type IS '消息类型：task/result/error/heartbeat';
COMMENT ON COLUMN agent_messages.payload IS '消息内容';
COMMENT ON COLUMN agent_messages.parent_task_id IS '关联的父任务ID';

-- ============================================
-- 表4: audit_logs - 审计日志表
-- ============================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    agent VARCHAR(50),
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE audit_logs IS '审计日志表，记录系统操作事件';
COMMENT ON COLUMN audit_logs.event_type IS '事件类型';
COMMENT ON COLUMN audit_logs.agent IS '涉及的Agent';
COMMENT ON COLUMN audit_logs.details IS '事件详情';

-- ============================================
-- 索引定义
-- ============================================

-- conversations索引
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at 
    ON conversations(updated_at DESC);

-- tasks索引
CREATE INDEX IF NOT EXISTS idx_tasks_conversation_id 
    ON tasks(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status 
    ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at 
    ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_type_status 
    ON tasks(task_type, status);

-- agent_messages索引
CREATE INDEX IF NOT EXISTS idx_agent_messages_task_id 
    ON agent_messages(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_from_agent 
    ON agent_messages(from_agent);
CREATE INDEX IF NOT EXISTS idx_agent_messages_to_agent 
    ON agent_messages(to_agent);
CREATE INDEX IF NOT EXISTS idx_agent_messages_created_at 
    ON agent_messages(created_at DESC);

-- audit_logs索引
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type 
    ON audit_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_agent 
    ON audit_logs(agent);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at 
    ON audit_logs(created_at DESC);

-- ============================================
-- 视图定义
-- ============================================

-- 任务概览视图
CREATE OR REPLACE VIEW task_overview AS
SELECT 
    t.id,
    t.conversation_id,
    c.title as conversation_title,
    t.task_type,
    t.status,
    t.created_at,
    t.started_at,
    t.completed_at,
    EXTRACT(EPOCH FROM (COALESCE(t.completed_at, CURRENT_TIMESTAMP) - COALESCE(t.started_at, t.created_at))) as duration_seconds
FROM tasks t
LEFT JOIN conversations c ON t.conversation_id = c.id
ORDER BY t.created_at DESC;

-- Agent活动统计视图
CREATE OR REPLACE VIEW agent_activity_stats AS
SELECT 
    from_agent as agent_name,
    COUNT(*) as total_messages,
    COUNT(DISTINCT parent_task_id) as tasks_handled,
    MIN(created_at) as first_activity,
    MAX(created_at) as last_activity
FROM agent_messages
GROUP BY from_agent;

-- ============================================
-- 初始数据
-- ============================================

-- 创建一个默认对话（用于系统测试）
INSERT INTO conversations (id, title) 
VALUES ('00000000-0000-0000-0000-000000000000', '系统默认对话')
ON CONFLICT (id) DO NOTHING;

PRINT 'Database schema initialized successfully!';
