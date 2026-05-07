"""
API Routes
API路由 - FastAPI端点定义
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional, List, AsyncGenerator
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# 路由实例
router = APIRouter()

# 全局状态（由main.py注入）
_supervisor = None
_redis_manager = None
_postgres_storage = None
_rag_service = None
_memory_manager = None
_skill_manager = None
_metrics_collector = None


def set_dependencies(
    supervisor,
    redis_manager,
    postgres_storage,
    rag_service=None,
    memory_manager=None,
    skill_manager=None,
    metrics_collector=None
):
    """注入依赖"""
    global _supervisor, _redis_manager, _postgres_storage
    global _rag_service, _memory_manager, _skill_manager, _metrics_collector
    _supervisor = supervisor
    _redis_manager = redis_manager
    _postgres_storage = postgres_storage
    _rag_service = rag_service
    _memory_manager = memory_manager
    _skill_manager = skill_manager
    _metrics_collector = metrics_collector


# ========== Request/Response Models ==========

class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    """聊天响应"""
    conversation_id: str
    task_id: str
    message: str


class ConversationResponse(BaseModel):
    """对话响应"""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str
    phase: Optional[str] = None
    progress: Optional[dict] = None


class AgentStatusResponse(BaseModel):
    """Agent状态响应"""
    agents: List[dict]


# ========== Chat Endpoints ==========

@router.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """发送聊天消息并获取响应"""
    if not _supervisor:
        raise HTTPException(status_code=500, detail="System not initialized")
    
    # 创建或获取对话ID
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = _postgres_storage.create_conversation(
            title=request.message[:50]
        )
    else:
        _postgres_storage.update_conversation(conversation_id)
    
    # 创建任务
    task_id = str(uuid.uuid4())
    
    # 在后台执行任务
    async def run_task():
        try:
            await _supervisor.process(
                user_input=request.message,
                conversation_id=conversation_id,
                task_id=task_id
            )
        except Exception as e:
            print(f"[API] Task error: {e}")
            _redis_manager.update_task_state_field(task_id, 'error', str(e))
    
    asyncio.create_task(run_task())
    
    return ChatResponse(
        conversation_id=conversation_id,
        task_id=task_id,
        message="任务已提交，正在处理中..."
    )


@router.get("/api/v1/conversations", response_model=List[ConversationResponse])
async def list_conversations(limit: int = 50):
    """获取对话列表"""
    conversations = _postgres_storage.list_conversations(limit)
    return [
        ConversationResponse(
            id=c['id'],
            title=c['title'],
            created_at=c['created_at'],
            updated_at=c['updated_at']
        )
        for c in conversations
    ]


@router.get("/api/v1/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """获取对话详情"""
    conversation = _postgres_storage.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    tasks = _postgres_storage.list_tasks_by_conversation(conversation_id)
    
    return {
        "conversation": conversation,
        "tasks": tasks
    }


# ========== Task Endpoints ==========

@router.get("/api/v1/tasks/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """获取任务状态"""
    task = _postgres_storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 从Redis获取实时状态
    redis_state = _redis_manager.get_task_state(task_id) or {}
    
    return TaskStatusResponse(
        task_id=task_id,
        status=task['status'],
        phase=redis_state.get('phase'),
        progress={
            'total_tasks': redis_state.get('total_tasks'),
            'completed_tasks': redis_state.get('completed_tasks'),
            'running_tasks': redis_state.get('running_tasks')
        }
    )


@router.get("/api/v1/tasks/{task_id}/collaboration")
async def get_task_collaboration(task_id: str):
    """获取任务协作详情（用于可视化）"""
    snapshot = _redis_manager.get_collaboration_snapshot(task_id)
    return snapshot


# ========== Agent Endpoints ==========

@router.get("/api/v1/agents/status", response_model=AgentStatusResponse)
async def get_agents_status():
    """获取所有Agent状态"""
    status = _redis_manager.get_all_agent_status()
    return AgentStatusResponse(
        agents=[
            {"name": name, **info}
            for name, info in status.items()
        ]
    )


# ========== WebSocket Events ==========

class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        """广播消息到所有连接"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@router.websocket("/api/v1/events")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket实时事件流"""
    await manager.connect(websocket)
    
    try:
        # 订阅Redis事件
        queue = await _redis_manager.subscribe([
            'task_state', 'task_update', 'agent_status', 'blackboard_write'
        ])
        
        while True:
            # 等待事件
            event = await queue.get()
            await websocket.send_json(event)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
        manager.disconnect(websocket)


# ========== RAG Endpoints ==========

@router.post("/api/v1/rag/search")
async def rag_search(request: dict):
    """双路混合RAG检索，支持指定知识库"""
    if _rag_service:
        result = await _rag_service.search(
            query=request.get("query", ""),
            fusion_method=request.get("fusion_method", "rrf"),
            top_k=request.get("top_k", 5),
            kb_name=request.get("kb_name", "default")
        )
        return result
    return {
        "query": request.get("query", ""),
        "results": [],
        "sources": [],
        "context": "RAG服务未就绪",
        "total_found": 0
    }


@router.get("/api/v1/rag/documents")
async def rag_list_documents(kb_name: str = None):
    """列出RAG知识库文档，可按知识库筛选"""
    if _rag_service:
        docs = _rag_service.list_documents(kb_name=kb_name)
        return {"documents": docs, "total": len(docs)}
    return {"documents": [], "total": 0}


@router.get("/api/v1/rag/knowledge-bases")
async def rag_list_knowledge_bases():
    """列出所有知识库"""
    if _rag_service:
        kbs = _rag_service.list_knowledge_bases()
        return {"knowledge_bases": kbs, "total": len(kbs)}
    return {"knowledge_bases": [], "total": 0}


@router.post("/api/v1/rag/documents/import")
async def rag_import_document(file_path: str = None, kb_name: str = "default"):
    """导入文档到指定知识库"""
    if _rag_service and file_path:
        doc = await _rag_service.import_document(file_path, kb_name=kb_name)
        if doc:
            return {"status": "ok", "document": doc.to_dict()}
        return {"status": "error", "message": "文档导入失败"}
    return {"status": "ok", "message": "文档导入接口已就绪"}


@router.post("/api/v1/rag/answer/stream")
async def rag_answer_stream(request: dict):
    """RAG流式问答（SSE）"""
    if not _rag_service:
        return StreamingResponse(
            _sse_error("RAG服务未就绪"),
            media_type="text/event-stream"
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in _rag_service.stream_answer(
            query=request.get("query", ""),
            llm_client=getattr(_rag_service, 'llm', None),
            max_sources=request.get("max_sources", 5),
            kb_name=request.get("kb_name", "default"),
            min_confidence=request.get("min_confidence")
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


async def _sse_error(message: str) -> AsyncGenerator[str, None]:
    yield f"data: {json.dumps({'type': 'error', 'message': message}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


# ========== Memory Endpoints ==========

@router.get("/api/v1/memory/skills")
async def memory_list_skills():
    """获取技能模板列表"""
    if _skill_manager and _memory_manager:
        skills = await _memory_manager.get_skill_templates(min_success_rate=0.0)
        return {"skills": skills, "total": len(skills)}
    return {"skills": [], "total": 0}


@router.get("/api/v1/memory/skills/stats")
async def memory_skill_stats():
    """获取技能系统统计"""
    if _skill_manager:
        return _skill_manager.get_skill_stats()
    return {
        "total_skills": 0, "active_skills": 0, "pruned_skills": 0,
        "total_evaluations": 0, "auto_generated": 0
    }


@router.get("/api/v1/memory/sessions/{session_id}")
async def memory_get_session(session_id: str):
    """获取会话记忆"""
    if _memory_manager:
        context = await _memory_manager.get_session_context(session_id)
        history = await _memory_manager.get_conversation_history(session_id)
        return {"session_id": session_id, "context": context, "history": history}
    return {"session_id": session_id, "context": {}, "history": []}


# ========== SSE Events ==========

async def event_generator(request):
    """SSE事件生成器"""
    queue = await _redis_manager.subscribe([
        'task_state', 'agent_status'
    ])
    
    while True:
        event = await queue.get()
        yield {
            "event": event.get('type', 'message'),
            "data": str(event)
        }


@router.get("/api/v1/events/sse")
async def sse_events():
    """SSE事件端点"""
    return EventSourceResponse(event_generator)


# ========== Health Check ==========

@router.get("/health")
async def health_check():
    """服务健康检查"""
    if _metrics_collector:
        return _metrics_collector.get_health_status()
    from monitoring import get_metrics_collector
    return get_metrics_collector().get_health_status()


@router.get("/health/ready")
async def readiness_check():
    """Kubernetes就绪检查"""
    checks = {}
    try:
        checks['redis'] = _redis_manager and _redis_manager.client.ping()
    except Exception:
        checks['redis'] = False
    try:
        checks['postgres'] = _postgres_storage and _postgres_storage.conn and not _postgres_storage.conn.closed
    except Exception:
        checks['postgres'] = False

    all_ready = all(checks.values())
    status_code = 200 if all_ready else 503
    return {"ready": all_ready, "checks": checks}, status_code


@router.get("/health/live")
async def liveness_check():
    """Kubernetes存活检查"""
    return {"alive": True}


@router.get("/metrics")
async def metrics():
    """Prometheus指标导出"""
    from fastapi.responses import PlainTextResponse
    collector = _metrics_collector
    if collector is None:
        from monitoring import get_metrics_collector
        collector = get_metrics_collector()
    return PlainTextResponse(content=collector.get_prometheus_metrics())


# ========== Dashboard ==========

@router.get("/")
async def dashboard():
    """Dashboard首页"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Multi-Agent System Dashboard</title>
        <meta charset="utf-8">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0f0f1a;
                color: #fff;
                min-height: 100vh;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px 40px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            }
            .header h1 { font-size: 24px; margin-bottom: 5px; }
            .header p { opacity: 0.8; font-size: 14px; }
            .container { max-width: 1400px; margin: 0 auto; padding: 20px 40px; }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 20px;
            }
            .card {
                background: #1a1a2e;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            }
            .card h2 { font-size: 16px; color: #aaa; margin-bottom: 15px; }
            .agent-item {
                display: flex;
                align-items: center;
                padding: 12px;
                background: #25253a;
                border-radius: 8px;
                margin-bottom: 10px;
            }
            .status-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 12px;
            }
            .status-online { background: #4ade80; }
            .status-busy { background: #facc15; }
            .status-offline { background: #6b7280; }
            .chat-container {
                background: #1a1a2e;
                border-radius: 12px;
                padding: 20px;
            }
            .chat-messages { min-height: 300px; max-height: 500px; overflow-y: auto; margin-bottom: 15px; }
            .message { padding: 12px 16px; border-radius: 12px; margin-bottom: 10px; max-width: 80%; }
            .message-user { background: #667eea; margin-left: auto; }
            .message-assistant { background: #25253a; }
            .chat-input { display: flex; gap: 10px; }
            .chat-input input {
                flex: 1;
                padding: 12px 16px;
                border: none;
                border-radius: 8px;
                background: #25253a;
                color: #fff;
                font-size: 14px;
            }
            .chat-input button {
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #fff;
                font-weight: 600;
                cursor: pointer;
            }
            .task-list { max-height: 400px; overflow-y: auto; }
            .task-item {
                padding: 15px;
                background: #25253a;
                border-radius: 8px;
                margin-bottom: 10px;
            }
            .task-status {
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                margin-left: 10px;
            }
            .task-pending { background: #6b7280; }
            .task-running { background: #facc15; color: #000; }
            .task-completed { background: #4ade80; color: #000; }
            .task-failed { background: #ef4444; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🤖 Multi-Agent 协作系统</h1>
            <p>基于 LangGraph + MCP + PostgreSQL + Redis</p>
        </div>
        <div class="container">
            <div class="grid">
                <div class="card">
                    <h2>📊 系统状态</h2>
                    <div id="system-status">加载中...</div>
                </div>
                <div class="card">
                    <h2>🤝 Agents</h2>
                    <div id="agents-list">加载中...</div>
                </div>
                <div class="card">
                    <h2>📈 协作状态</h2>
                    <div id="collaboration-status">选择一个任务查看</div>
                </div>
            </div>
            <div class="grid">
                <div class="chat-container">
                    <h2 style="margin-bottom: 15px;">💬 对话</h2>
                    <div class="chat-messages" id="chat-messages">
                        <div class="message message-assistant">你好！我是多Agent协作系统的助手。有什么可以帮你的吗？</div>
                    </div>
                    <div class="chat-input">
                        <input type="text" id="chat-input" placeholder="输入消息..." />
                        <button onclick="sendMessage()">发送</button>
                    </div>
                </div>
                <div class="card">
                    <h2>📋 任务列表</h2>
                    <div class="task-list" id="task-list">暂无任务</div>
                </div>
            </div>
        </div>
        <script>
            // 轮询获取状态
            async function fetchStatus() {
                try {
                    const res = await fetch('/api/v1/agents/status');
                    const data = await res.json();
                    renderSystemStatus(data.agents);
                    renderAgents(data.agents);
                } catch (e) { console.error(e); }
            }
            
            function renderSystemStatus(agents) {
                const container = document.getElementById('system-status');
                const total = agents.length;
                const online = agents.filter(a => a.status === 'online' || a.status === 'busy').length;
                container.innerHTML = `
                    <div style="display:flex;justify-content:space-between;margin-bottom:8px">
                        <span>🤖 Agent总数</span><span>${total}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;margin-bottom:8px">
                        <span>✅ 在线</span><span style="color:#4ade80">${online}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;margin-bottom:8px">
                        <span>⏱️ 离线</span><span style="color:#6b7280">${total - online}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between">
                        <span>📊 系统</span><span style="color:#4ade80">运行正常</span>
                    </div>
                `;
            }
            
            function renderAgents(agents) {
                const container = document.getElementById('agents-list');
                container.innerHTML = agents.map(a => `
                    <div class="agent-item">
                        <div class="status-dot status-${a.status || 'offline'}"></div>
                        <div>
                            <strong>${a.name}</strong>
                            <div style="font-size: 12px; color: #888;">${a.status || 'offline'}</div>
                        </div>
                    </div>
                `).join('');
            }
            
            async function sendMessage() {
                const input = document.getElementById('chat-input');
                const msg = input.value.trim();
                if (!msg) return;
                
                // 添加用户消息
                addMessage(msg, 'user');
                input.value = '';
                
                // 发送请求
                try {
                    const res = await fetch('/api/v1/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: msg })
                    });
                    const data = await res.json();
                    
                    // 轮询任务状态
                    pollTask(data.task_id);
                } catch (e) { console.error(e); }
            }
            
            function addMessage(text, type) {
                const container = document.getElementById('chat-messages');
                const div = document.createElement('div');
                div.className = 'message message-' + type;
                div.textContent = text;
                container.appendChild(div);
                container.scrollTop = container.scrollHeight;
            }
            
            async function pollTask(taskId) {
                // 简化实现
                addMessage('任务处理中...', 'assistant');
            }
            
            // 初始化
            fetchStatus();
            setInterval(fetchStatus, 5000);
            
            // 回车发送
            document.getElementById('chat-input').addEventListener('keypress', e => {
                if (e.key === 'Enter') sendMessage();
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/dashboard")
async def dashboard_alias():
    """Dashboard别名"""
    return await dashboard()
