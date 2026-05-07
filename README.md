# Multi-Agent Collaboration System
# 多Agent协作系统

## 项目概述

这是一个基于 LangGraph + MCP + PostgreSQL + Redis 的多Agent协作系统，灵感来源于 Cursor，旨在实现通用Agent框架。

### 核心特性

- 🚀 **LangGraph 工作流编排**：有状态的多Agent协作，支持条件分支、循环、并行执行
- 🔧 **MCP 工具标准协议**：统一的工具接口，支持复用社区MCP Server
- 💾 **PostgreSQL 持久化存储**：对话历史、任务记录、审计日志
- ⚡ **Redis 实时状态管理**：Agent协作状态、消息队列、实时通知
- 📊 **可视化Dashboard**：实时展示Agent协作状态和进度

### 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      用户界面层                          │
│                  (Web Dashboard / API)                   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                      API 服务层                          │
│              (FastAPI + WebSocket SSE)                   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   LangGraph 编排层                       │
│                    (总控Agent Supervisor)                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                 │
│  │ Search  │  │  Code   │  │   Doc   │  ... 工作Agents │
│  │ Agent   │  │ Agent   │  │ Agent   │                 │
│  └─────────┘  └─────────┘  └─────────┘                 │
└─────────────────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                      MCP 工具层                          │
│        (文件系统 / 搜索 / 数据库 / Web Fetch)            │
└─────────────────────────────────────────────────────────┘
         │              │
         ▼              ▼
┌─────────────────┐  ┌─────────────────────────────────────┐
│   Redis         │  │        PostgreSQL                   │
│  (实时状态)      │  │      (持久化存储)                   │
└─────────────────┘  └─────────────────────────────────────┘
```

### Agent角色

| Agent | 职责 | 核心工具 |
|-------|------|----------|
| Supervisor | 任务拆解、分配、结果整合 | 调度所有Worker |
| Search | 网络搜索、信息获取 | Web搜索、网页抓取 |
| Code | 代码编写、执行、优化 | 文件操作、代码执行 |
| Doc | 文档生成、总结、整理 | 文件读写、格式化 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
# PostgreSQL 数据库初始化
psql -U postgres -c "CREATE DATABASE multi_agent_db;"
psql -U postgres -d multi_agent_db -f migrations/001_init.sql
```

### 3. 启动服务

```bash
# 启动Redis（如果未运行）
service redis-server start

# 启动应用
python -m src.main
```

服务将在 `http://localhost:5002` 启动。

### 4. 访问 Dashboard

打开浏览器访问 `http://your-server:5002` 查看可视化Dashboard。

## API 文档

启动服务后访问：
- Swagger UI: `http://localhost:5002/docs`
- ReDoc: `http://localhost:5002/redoc`

### 核心接口

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/chat` | 发送对话请求 |
| GET | `/api/v1/conversations` | 获取对话列表 |
| GET | `/api/v1/conversations/{id}` | 获取对话历史 |
| GET | `/api/v1/tasks/{id}/status` | 查询任务状态 |
| GET | `/api/v1/agents/status` | 获取Agent状态 |
| WS | `/api/v1/events` | WebSocket实时事件流 |

## 配置说明

所有配置通过 `config.yaml` 文件管理，详见文件内注释。

关键配置项：
- `app.port`: 服务端口，默认5002
- `database.*`: PostgreSQL连接信息
- `redis.*`: Redis连接信息
- `agents.*`: Agent模型和参数配置
- `mcp.servers`: MCP服务器列表

## 项目结构

```
multi-agent-system/
├── README.md
├── requirements.txt
├── config.yaml
├── src/
│   ├── __init__.py
│   ├── main.py              # 应用入口
│   ├── supervisor/          # 总控Agent
│   │   ├── __init__.py
│   │   ├── agent.py         # Supervisor核心逻辑
│   │   └── prompts.py       # 提示词模板
│   ├── workers/             # 工作Agents
│   │   ├── __init__.py
│   │   ├── base.py           # Worker基类
│   │   ├── search_agent.py   # 搜索Agent
│   │   ├── code_agent.py     # 代码Agent
│   │   └── doc_agent.py      # 文档Agent
│   ├── mcp/                 # MCP集成
│   │   ├── __init__.py
│   │   └── servers.py       # MCP服务器管理
│   ├── storage/             # 存储层
│   │   ├── __init__.py
│   │   ├── postgres.py       # PostgreSQL操作
│   │   └── redis_manager.py  # Redis操作
│   └── api/                 # API层
│       ├── __init__.py
│       └── routes.py        # 路由和端点
├── migrations/              # 数据库迁移
│   └── 001_init.sql
└── tests/                   # 测试
    └── test_agents.py
```

## 数据库设计

### PostgreSQL 表结构

#### conversations - 对话记录
| 字段 | 类型 | 描述 |
|------|------|------|
| id | UUID | 主键 |
| title | VARCHAR(255) | 对话标题 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### tasks - 任务记录
| 字段 | 类型 | 描述 |
|------|------|------|
| id | UUID | 主键 |
| conversation_id | UUID | 所属对话 |
| task_type | VARCHAR(50) | 任务类型 |
| status | VARCHAR(20) | 状态 |
| result | JSONB | 结果 |
| created_at | TIMESTAMP | 创建时间 |
| completed_at | TIMESTAMP | 完成时间 |

#### agent_messages - Agent间消息
| 字段 | 类型 | 描述 |
|------|------|------|
| id | SERIAL | 主键 |
| from_agent | VARCHAR(50) | 来源Agent |
| to_agent | VARCHAR(50) | 目标Agent |
| message_type | VARCHAR(20) | 消息类型 |
| payload | JSONB | 消息内容 |
| created_at | TIMESTAMP | 创建时间 |

### Redis 数据结构

| Key | 类型 | 描述 |
|-----|------|------|
| `mas:task:{id}:state` | Hash | 任务实时状态 |
| `mas:agent:{name}:status` | String | Agent在线状态 |
| `mas:blackboard:{task_id}` | Hash | 共享中间结果 |
| `mas:events` | Pub/Sub | 状态变更事件流 |

## 开发指南

### 添加新的Worker Agent

1. 在 `src/workers/` 创建新的Agent文件，继承 `BaseWorker`
2. 在 `config.yaml` 的 `agents.workers` 中添加配置
3. 在 `src/supervisor/agent.py` 中注册该Agent

示例：
```python
# src/workers/my_agent.py
from .base import BaseWorker

class MyAgent(BaseWorker):
    name = "my_agent"
    description = "我的自定义Agent"
    
    async def execute(self, task: dict, context: dict) -> dict:
        # 实现任务执行逻辑
        return {"result": "done"}
```

### 扩展MCP工具

在 `config.yaml` 的 `mcp.servers` 中添加新的MCP服务器配置。

## License

MIT
