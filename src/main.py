"""
Multi-Agent System Main Entry
多Agent协作系统主入口
"""

import asyncio
import yaml
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from storage import get_storage, get_redis
from workers import SearchAgent, CodeAgent, DocAgent
from supervisor import SupervisorAgent
from api import router, set_dependencies


# 全局实例
config = None
postgres_storage = None
redis_manager = None
supervisor = None


def load_config() -> dict:
    """加载配置文件"""
    config_path = Path(__file__).parent.parent / 'config.yaml'
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global config, postgres_storage, redis_manager, supervisor
    
    print("=" * 50)
    print("🚀 Multi-Agent System 启动中...")
    print("=" * 50)
    
    # 加载配置
    config = load_config()
    print(f"📁 配置文件加载成功")
    
    # 初始化存储层
    postgres_storage = get_storage(config['database'])
    
    # 初始化数据库表
    try:
        postgres_storage.init_tables()
    except Exception as e:
        print(f"⚠️  初始化表可能已存在: {e}")
    
    # 初始化Redis
    redis_manager = get_redis(config['redis'])
    print(f"✅ Redis 连接成功")
    
    # 初始化Workers
    workers_config = config.get('agents', {}).get('workers', [])
    workers = {}
    
    for wc in workers_config:
        name = wc.get('name')
        worker_config = {**wc, **config.get('workers', {}).get(name, {})}
        
        # 额外配置
        if name == 'search':
            worker_config['tavily'] = config.get('tavily', {})
        
        if name == 'search':
            workers[name] = SearchAgent(worker_config, redis_manager, postgres_storage)
        elif name == 'code':
            workers[name] = CodeAgent(worker_config, redis_manager, postgres_storage)
        elif name == 'doc':
            workers[name] = DocAgent(worker_config, redis_manager, postgres_storage)
        
        # 初始化Worker
        if name in workers:
            await workers[name].initialize()
    
    print(f"✅ Workers 初始化完成: {list(workers.keys())}")
    
    # 初始化Supervisor
    supervisor_config = config.get('agents', {}).get('supervisor', {})
    supervisor = SupervisorAgent(
        supervisor_config,
        workers,
        redis_manager,
        postgres_storage
    )
    print(f"✅ Supervisor 初始化完成")
    
    # 设置API依赖
    set_dependencies(supervisor, redis_manager, postgres_storage)
    
    # 标记所有Agent就绪
    for name in workers:
        redis_manager.mark_agent_idle(name)
    
    print("=" * 50)
    print(f"🎉 系统启动完成! 访问 http://0.0.0.0:{config['app']['port']}")
    print("=" * 50)
    
    yield
    
    # 关闭时清理
    print("\n🛑 系统关闭中...")
    
    for name, worker in workers.items():
        await worker.shutdown()
    
    if redis_manager:
        redis_manager.close()
    
    if postgres_storage:
        postgres_storage.close()
    
    print("👋 系统已关闭")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="Multi-Agent Collaboration System",
        description="基于 LangGraph + MCP + PostgreSQL + Redis 的多Agent协作系统",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册路由
    app.include_router(router)
    
    return app


# 创建应用实例
app = create_app()


def main():
    """主入口"""
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
