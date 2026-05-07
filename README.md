# Multi-Agent Collaboration System / 多Agent协作系统

## 项目概述

基于 **LangGraph + MCP + PostgreSQL + Redis + Milvus + Neo4j** 的多Agent协作系统，灵感来源于 Cursor，实现通用Agent框架。

### 核心特性

- 🧠 **LangGraph 工作流编排**：有状态的多Agent协作，支持条件分支、循环、并行执行
- 🔧 **MCP 工具标准协议**：统一的工具接口，支持复用社区MCP Server
- 📚 **RAG 混合检索**：向量检索 (Milvus) + 知识图谱检索 (Neo4j) + 多路融合排序 (RRF)
- 🗄️ **分层记忆系统** (Hermes架构)：会话记忆 (Redis) / 技能记忆 (PostgreSQL) / 长期记忆 (Milvus+Neo4j)
- 📊 **Prometheus 监控**：CPU / 内存 / 磁盘指标采集与导出
- 🐳 **Docker 一键部署**：全栈容器化，含 PostgreSQL (pgvector)、Redis、Milvus、Neo4j、Nginx

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                 用户界面层 (Nginx + Dashboard)            │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              API 服务层 (FastAPI + WebSocket SSE)         │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  LangGraph 编排层                         │
│                   (Supervisor 总控Agent)                  │
│  ┌──────────┐ ┌──────┐ ┌──────┐ ┌───────────┐          │
│  │  Search  │ │ Code │ │ Doc  │ │ Reasoning │          │
│  │  Agent   │ │Agent │ │Agent │ │  Agent    │          │
│  └──────────┘ └──────┘ └──────┘ └───────────┘          │
│  ┌──────────────────────┐                               │
│  │     RAG Agent        │                               │
│  └──────────────────────┘                               │
└─────────────────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                    MCP 工具层                             │
│  (filesystem / duckduckgo / milvus / neo4j)             │
└─────────────────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌───────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐ ┌──────┐
│  Redis    │ │PostgreSQL│ │ Milvus   │ │Neo4j │ │MinIO │
│ (实时状态) │ │ (持久化)  │ │(向量检索) │ │(图谱) │ │(对象) │
└───────────┘ └──────────┘ └──────────┘ └──────┘ └──────┘
```

## Agent 角色

| Agent | 职责 | 核心工具 |
|-------|------|----------|
| **Supervisor** | 任务拆解、分配、结果整合 | 调度所有Worker |
| **Search** | 网络搜索、信息获取 | Web搜索 (DuckDuckGo)、网页抓取 |
| **Code** | 代码编写、执行、优化 | 文件读写、代码执行 |
| **Doc** | 文档生成、总结、整理 | 文件读写、格式化 |
| **Reasoning** | 逻辑推理、结果校验、质量评估 | 逻辑分析、错误检测 |
| **RAG** | 文档检索、知识问答 | 向量检索 + 图谱检索 + 融合排序 |

## 快速开始

### Docker 一键部署（推荐）

```bash
docker-compose up -d
```

启动后访问 `http://localhost` 进入 Dashboard。

### 手动部署

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 启动依赖服务

确保以下服务已运行：
- PostgreSQL 16 (需安装 pgvector 扩展)
- Redis 7+
- Milvus 2.4+ (需 etcd + MinIO)
- Neo4j 5.20+

#### 3. 初始化数据库

```bash
psql -U postgres -c "CREATE DATABASE multi_agent_db;"
psql -U postgres -d multi_agent_db -f migrations/001_init.sql
```

#### 4. 启动应用

```bash
python -m src.main
```

服务在 `http://localhost:5002` 启动。

## API 文档

启动后访问：
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
| WS | `/api/v1/events` | WebSocket 实时事件流 |

## 配置说明

所有配置通过 `config.yaml` 管理，关键配置项：

| 配置段 | 说明 |
|--------|------|
| `app` | 服务端口、日志级别 |
| `database` | PostgreSQL 连接信息 |
| `redis` | Redis 连接信息 |
| `tavily` | Tavily 搜索 API |
| `minimax` | MiniMax 模型 API |
| `milvus` | Milvus 向量数据库连接 (dim=1024) |
| `neo4j` | Neo4j 图数据库连接 |
| `embedding` | BGE 嵌入模型配置 (BAAI/bge-large-zh-v1.5) |
| `rag` | RAG 分块/检索/融合参数 |
| `memory` | 记忆系统 TTL、阈值参数 |
| `mcp.servers` | MCP 服务器列表 |
| `agents` | Agent 模型和参数配置 |
| `supervisor` | 总控Agent 系统提示词 |
| `workers` | 各 Worker Agent 角色描述和提示词 |

## 项目结构

```
multi-agent-system/
├── README.md
├── requirements.txt
├── config.yaml                 # 全局配置文件
├── Dockerfile                  # 应用镜像
├── docker-compose.yml          # 全栈编排 (含 PG/Redis/Milvus/Neo4j)
├── frontend/
│   ├── index.html              # Dashboard 页面
│   ├── server.js               # 前端开发服务器
│   └── src/
│       ├── app.js / app.jsx    # 前端主逻辑
│       └── styles.css          # 样式
├── migrations/
│   └── 001_init.sql            # 数据库初始化脚本
├── nginx/
│   └── nginx.conf              # Nginx 反向代理配置
├── src/
│   ├── __init__.py
│   ├── main.py                 # 应用入口
│   ├── supervisor/             # 总控Agent
│   │   ├── agent.py            # Supervisor 核心逻辑
│   │   └── prompts.py          # 提示词模板
│   ├── workers/                # 工作Agent
│   │   ├── base.py             # Worker 基类
│   │   ├── search_agent.py     # 搜索Agent
│   │   ├── code_agent.py       # 代码Agent
│   │   ├── doc_agent.py        # 文档Agent
│   │   └── reasoning_agent.py  # 推理校验Agent
│   ├── rag/                    # RAG 检索模块
│   │   ├── document_loader.py  # 文档加载 (PDF/Word/MD)
│   │   ├── vector_store.py     # Milvus 向量存储
│   │   ├── kg_retriever.py     # Neo4j 知识图谱检索
│   │   ├── retrieval_fusion.py # 多路融合排序 (RRF)
│   │   └── rag_service.py      # RAG 核心服务
│   ├── memory/                 # 分层记忆系统 (Hermes)
│   │   ├── memory_manager.py   # 三层记忆管理器
│   │   └── skill_manager.py    # 技能模板管理
│   ├── llm/                    # LLM 集成
│   │   └── embeddings.py       # BGE 嵌入模型封装
│   ├── mcp/                    # MCP 协议集成
│   │   └── servers.py          # MCP 服务器管理
│   ├── storage/                # 存储层
│   │   ├── postgres.py         # PostgreSQL 操作
│   │   ├── redis_manager.py    # Redis 操作
│   │   ├── milvus_manager.py   # Milvus 向量库操作
│   │   ├── neo4j_manager.py    # Neo4j 图库操作
│   │   └── artifact_store.py   # MinIO 文件存储
│   ├── monitoring/             # 监控模块
│   │   └── metrics.py          # Prometheus 指标采集
│   └── api/                    # API 层
│       └── routes.py           # 路由和端点
└── tests/
    └── test_agents.py          # Agent 单元测试
```

## 数据库设计

### PostgreSQL 表结构

| 表名 | 描述 |
|------|------|
| `conversations` | 对话记录 |
| `tasks` | 任务记录（含 payload、result、状态流转） |
| `agent_messages` | Agent 间通信消息 |
| `audit_logs` | 系统审计日志 |
| `skill_templates` | 技能模板（提示词 + 工具序列 + 成功率） |
| `skill_evaluations` | 技能执行质量评估 |
| `long_term_memories` | 长期记忆存储 |

内置 `task_overview` 和 `agent_activity_stats` 视图，方便查询任务概览和Agent活动统计。

### Redis 数据结构

| Key | 类型 | 描述 |
|-----|------|------|
| `mas:task:{id}:state` | Hash | 任务实时状态 |
| `mas:agent:{name}:status` | String | Agent 在线状态 |
| `mas:blackboard:{task_id}` | Hash | 共享中间结果 (黑板模式) |
| `mas:events` | Pub/Sub | 状态变更事件流 |
| `mas:session:{id}` | Hash | 会话上下文 (TTL) |

### Milvus 向量存储

用于 RAG 语义检索和长期记忆的向量化存储，嵌入维度 1024 (BGE-large-zh-v1.5)。

### Neo4j 知识图谱

存储文档实体关系、Agent 协作关系图，支持图谱遍历检索。

## 记忆系统 (Hermes 架构)

```
┌─ 会话记忆 (Session) ──────────────────┐
│  Redis — 临时上下文、任务状态           │
│  TTL: 3600s                           │
├─ 技能记忆 (Skill) ────────────────────┤
│  PostgreSQL — 标准化工具调用模板        │
│  自动评估成功率，择优复用               │
├─ 长期记忆 (Long-term) ────────────────┤
│  Milvus (向量) + Neo4j (图谱)          │
│  全局知识与历史经验                     │
└───────────────────────────────────────┘
```

## 开发指南

### 添加新的 Worker Agent

1. 在 `src/workers/` 创建新的 Agent 文件，继承 `BaseWorker`
2. 在 `config.yaml` 的 `agents.workers` 和 `workers` 中添加配置
3. Superisor 会自动发现并调度

示例：

```python
# src/workers/my_agent.py
from .base import BaseWorker

class MyAgent(BaseWorker):
    name = "my_agent"
    description = "我的自定义Agent"

    async def execute(self, task: dict, context: dict) -> dict:
        return {"result": "done"}
```

### 扩展 MCP 工具

在 `config.yaml` 的 `mcp.servers` 中添加 MCP 服务器：

```yaml
mcp:
  servers:
    - name: "my-tool"
      command: "python"
      args: ["-m", "my_mcp_server"]
```

## License

MIT
