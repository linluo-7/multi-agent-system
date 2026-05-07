# RAG 商业化优化任务清单

> 最后更新: 2026-05-07 18:30

## 任务状态说明

- ⬜ 待开始
- 🔵 进行中
- ✅ 已完成
- ❌ 已取消

---

## P0 — 基础联通（RAG 接入 Agent 对话）

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| P0-1 | 新建 `src/workers/rag_agent.py` | ✅ | 继承 BaseWorker，封装 RAGService.search() 和 answer_question()，暴露 `rag_search` / `rag_qa` 两个 action |
| P0-2 | `src/main.py` 实例化 rag_agent | ✅ | worker 工厂加入 `elif name == 'rag'` 分支，注入 rag_service + llm_client |
| P0-3 | Supervisor 加入 RAG 路由 | ✅ | `agent.py` 规则路由加 `needs_rag` 关键词；`prompts.py` 可用 Agent 列表加入 rag；`_build_response` 处理 rag 结果 |
| P0-4 | 验证端到端链路 | ✅ | 代码链路贯通：对话提问 → Supervisor → RAG Agent → 返回答案（运行时需启动服务 + 导入文档验证） |

---

## P1 — 意图识别与动态路由

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| P1-1 | 意图分类器 | ✅ | 新建 `src/supervisor/intent_classifier.py`，关键词 + LLM 两级分类；Supervisor 集成到规则/LLM 规划器 |
| P1-2 | RAG → Search Fallback 链 | ✅ | `_execute_tasks` 完成后自动检测 `needs_fallback`，触发 Search Agent 补充，`_build_response` 展示融合结果 |
| P1-3 | 多知识库动态路由 | ✅ | RAGService / VectorStore / RAGAgent / API 全部支持 `kb_name` 参数；config.yaml 定义多知识库配置；新增 `GET /api/v1/rag/knowledge-bases` |
| P1-4 | 检索置信度阈值 | ✅ | config.yaml 新增 `min_score` / `min_results`；RAGAgent 从配置读取阈值，低于阈值自动标记 `needs_fallback: true` |

---

## P2 — 检索质量

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| P2-1 | Query 改写 | ✅ | 新建 `src/rag/query_rewriter.py`：多轮上下文改写(指代消解)、HyDE假设文档生成、子问题拆解(LLM+规则)；集成到RAGService.search() |
| P2-2 | BM25 + Dense 混合检索 | ✅ | 新建 `src/rag/sparse_retriever.py`：BM25关键词检索器；3路融合(vector+KG+sparse)→RRF/weighted排序 |
| P2-3 | Cross-encoder Re-rank | ✅ | 重写 `rerank_by_llm()`：LLM pointwise相关性打分 + 多样性重排(MMR)；集成到search()管线 |
| P2-4 | 语义分块 | ✅ | 重写 `_chunk_text()`：章节标题检测→段落分割→句子边界切分，保留文档层级结构前缀 |
| P2-5 | NER 实体抽取 | ✅ | `kg_retriever.py` 新增 `_extract_by_llm()`：LLM驱动实体+关系抽取；regex规则作为fallback |
| P2-6 | 父文档检索 | ✅ | 新增 `expand_to_parent_documents()`：chunk检索→扩展前后块+父文档原文上下文，集成到search()管线 |
| P2-7 | 多跳检索 | ✅ | 新增 `multi_hop_search()`：首轮检索→LLM生成下跳query→再检索→合并去重 |

---

## P3 — 答案生成质量

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| P3-1 | Inline citation | ⬜ | 答案中精确引用到 chunk/段落级别来源 |
| P3-2 | 拒答与降级 | ⬜ | 所有检索结果 score 低于阈值 → 拒答或降级为纯 LLM 回复 |
| P3-3 | 结构化输出 | ⬜ | 支持表格、列表、JSON 结构化返回 |
| P3-4 | 流式输出 (SSE) | ⬜ | RAG 答案走 SSE 流式返回，与 Agent 对话的 WebSocket 对齐 |

---

## P4 — 前端与数据工程

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| P4-1 | 知识库管理页面 | ⬜ | 前端新增页面：文档列表、预览、删除 |
| P4-2 | 文件上传（拖拽） | ⬜ | 前端拖拽上传 → 后端接收文件 → 自动索引 |
| P4-3 | URL 导入 | ⬜ | 输入 URL 自动抓取并索引文档 |
| P4-4 | 文档解析增强 | ⬜ | PDF 表格提取、图片 OCR、层级结构保留 |
| P4-5 | 增量索引管道 | ⬜ | 文件监听 / 定时扫描 / Webhook 触发增量更新 |
| P4-6 | 前端对话接入 RAG | ⬜ | ChatView 调用真实 Agent API，展示 RAG 来源引用 |

---

## P5 — 工程化与评估

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| P5-1 | RAG 全链路追踪 | ⬜ | 每次检索延迟、命中率、LLM token 消耗埋点 |
| P5-2 | RAGAS 评估体系 | ⬜ | faithfulness / relevance / precision 自动化评估 |
| P5-3 | 语义缓存 | ⬜ | Redis 缓存高频查询 + 相似问去重 |
| P5-4 | 文档权限控制 | ⬜ | 知识库/文档级别 ACL |
| P5-5 | 用户反馈闭环 | ⬜ | 答案点赞/踩 → 反馈写入评估表，驱动 skill 优化 |

---

## 进度概览

```
P0 基础联通     [4/4]  ████████████████████  100%
P1 意图路由     [4/4]  ████████████████████  100%
P2 检索质量     [7/7]  ████████████████████  100%
P3 答案质量     [0/4]  ░░░░░░░░░░░░░░░░░░░░  0%
P4 前端与数据   [0/6]  ░░░░░░░░░░░░░░░░░░░░  0%
P5 工程化       [0/5]  ░░░░░░░░░░░░░░░░░░░░  0%
────────────────────────────────────────────
总计          [15/30] ██████████░░░░░░░░░░  50%
```

## 建议执行顺序

```
P0 (基础联通) → P1 (意图路由) → P2 (检索质量) → P3 (答案质量) → P4 (前端) → P5 (工程化)
```
