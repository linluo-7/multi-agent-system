"""
Multi-Agent System Main Entry
多Agent协作系统主入口 — 自主进化 + 双路RAG + 推理闭环
"""

import asyncio
import yaml
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from storage import get_storage, get_redis, get_milvus, get_neo4j
from workers import SearchAgent, CodeAgent, DocAgent, ReasoningAgent, RAGAgent
from supervisor import SupervisorAgent
from llm import get_llm
from llm.embeddings import get_embedding_service
from api import router, set_dependencies
from rag import RAGService
from memory import MemoryManager, SkillManager
from storage.artifact_store import get_artifact_store
from monitoring import get_metrics_collector


# 全局实例
config = None
postgres_storage = None
redis_manager = None
milvus_manager = None
neo4j_manager = None
embedding_service = None
rag_service = None
memory_manager = None
skill_manager = None
artifact_store = None
metrics_collector = None
supervisor = None


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / 'config.yaml'
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, postgres_storage, redis_manager
    global milvus_manager, neo4j_manager, embedding_service
    global rag_service, memory_manager, skill_manager
    global artifact_store, metrics_collector, supervisor

    print("=" * 60)
    print("  Multi-Agent System 启动中...")
    print("=" * 60)

    # 加载配置
    config = load_config()
    print(f"  [OK] 配置文件加载成功")

    # 监控采集器
    metrics_collector = get_metrics_collector()
    print(f"  [OK] 监控采集器启动")

    # 存储层
    postgres_storage = get_storage(config['database'])
    try:
        postgres_storage.init_tables()
    except Exception as e:
        print(f"  [WARN] 数据库表初始化: {e}")

    redis_manager = get_redis(config['redis'])
    print(f"  [OK] Redis 连接成功")

    # 向量数据库 & 图数据库
    milvus_manager = get_milvus(config.get('milvus', {}))
    await milvus_manager.connect()
    print(f"  [OK] Milvus 初始化完成")

    neo4j_manager = get_neo4j(config.get('neo4j', {}))
    await neo4j_manager.connect()
    print(f"  [OK] Neo4j 初始化完成")

    # Embedding 服务
    embedding_service = get_embedding_service(config.get('embedding', {}))
    await embedding_service.initialize()
    print(f"  [OK] Embedding 服务初始化完成 (dim={embedding_service.dim})")

    # RAG 服务
    rag_service = RAGService(
        config, milvus_manager, neo4j_manager, embedding_service,
        llm_client=llm_client
    )
    await rag_service.initialize()
    print(f"  [OK] 双路混合RAG服务初始化完成")

    # 记忆系统
    memory_manager = MemoryManager(
        config, redis_manager, postgres_storage,
        milvus_manager, neo4j_manager, embedding_service
    )
    skill_manager = SkillManager(config, memory_manager, postgres_storage, redis_manager)
    await skill_manager.initialize()
    print(f"  [OK] 三层记忆系统初始化完成")

    # 产物版本管理
    artifact_store = get_artifact_store(
        config.get('artifact', {}).get('storage_dir', '/tmp/artifacts')
    )
    print(f"  [OK] 产物版本管理初始化完成")

    # LLM 客户端
    llm_client = None
    if config.get('minimax', {}).get('api_key'):
        try:
            llm_client = get_llm(config['minimax'])
            print(f"  [OK] MiniMax LLM 初始化成功")
        except Exception as e:
            print(f"  [WARN] MiniMax LLM 初始化失败: {e}")

    # 初始化 Workers
    workers_config = config.get('agents', {}).get('workers', [])
    workers = {}

    for wc in workers_config:
        name = wc.get('name')
        worker_config = {**wc, **config.get('workers', {}).get(name, {})}

        if name == 'search':
            worker_config['tavily'] = config.get('tavily', {})
            workers[name] = SearchAgent(worker_config, redis_manager, postgres_storage)
        elif name == 'code':
            workers[name] = CodeAgent(worker_config, redis_manager, postgres_storage)
        elif name == 'doc':
            workers[name] = DocAgent(worker_config, redis_manager, postgres_storage)
        elif name == 'rag':
            workers[name] = RAGAgent(worker_config, redis_manager, postgres_storage,
                                     rag_service=rag_service, llm_client=llm_client)

        if name in workers:
            await workers[name].initialize()

    # Reasoning Agent
    reasoning_config = config.get('workers', {}).get('reasoning', {})
    reasoning_agent = ReasoningAgent(
        reasoning_config, redis_manager, postgres_storage, llm_client=llm_client
    )
    await reasoning_agent.initialize()
    workers['reasoning'] = reasoning_agent
    print(f"  [OK] Workers 初始化完成: {list(workers.keys())}")

    # Supervisor (带推理闭环)
    supervisor_config = config.get('agents', {}).get('supervisor', {})
    supervisor = SupervisorAgent(
        supervisor_config,
        workers,
        redis_manager,
        postgres_storage,
        llm_client=llm_client,
        reasoning_agent=reasoning_agent,
        artifact_store=artifact_store
    )
    print(f"  [OK] Supervisor 初始化完成 (推理闭环 + 自纠错)")

    # API 依赖注入
    set_dependencies(
        supervisor, redis_manager, postgres_storage,
        rag_service=rag_service,
        memory_manager=memory_manager,
        skill_manager=skill_manager,
        metrics_collector=metrics_collector
    )

    for name in workers:
        redis_manager.mark_agent_idle(name)

    print("=" * 60)
    print(f"  系统启动完成! http://0.0.0.0:{config['app']['port']}")
    print("=" * 60)

    yield

    print("\n系统关闭中...")
    for _, worker in workers.items():
        await worker.shutdown()
    if redis_manager:
        redis_manager.close()
    if postgres_storage:
        postgres_storage.close()
    if milvus_manager:
        await milvus_manager.close()
    if neo4j_manager:
        await neo4j_manager.close()
    print("系统已关闭")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Multi-Agent Collaboration System",
        description="基于 LangGraph + MCP 的多Agent协作系统 — "
                    "分层记忆 · 双路混合RAG · 推理闭环 · 自主进化",
        version="2.0.0",
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()


def main():
    config = load_config()
    uvicorn.run(
        "src.main:app",
        host=config['app']['host'],
        port=config['app']['port'],
        reload=config['app']['debug'],
        log_level=config['app']['log_level'].lower()
    )


if __name__ == "__main__":
    main()
