# RAG 商业化优化任务清单

> 最后更新: 2026-05-07 19:00 ✅ 全部完成

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
| P3-1 | Inline citation | ✅ | 系统提示词要求 `[1] [2]` 格式引用；来源列表编号映射；`_postprocess_citations()` 后处理补充缺失引用 |
| P3-2 | 拒答与降级 | ✅ | `_build_refusal()` 按置信度分级处理（无结果/低相关）；`_estimate_confidence()` 四级评分（high/medium/low/insufficient）；`min_confidence` 可配置 |
| P3-3 | 结构化输出 | ✅ | `output_format` 参数支持 markdown/table/json；系统提示词根据格式生成对应结构 |
| P3-4 | 流式输出 (SSE) | ✅ | 新增 `stream_answer()` 异步生成器；新增 `POST /api/v1/rag/answer/stream` SSE 端点；支持逐token流式 + 搜索元数据 |

---

## P4 — 前端与数据工程

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| P4-1 | 知识库管理页面 | ✅ | 前端新增 KnowledgeBaseView：知识库列表切换、文档列表/预览/删除 |
| P4-2 | 文件上传（拖拽） | ✅ | 前端拖拽上传 + 点击选择；后端 `POST /api/v1/rag/documents/upload` multipart接收；自动索引 |
| P4-3 | URL 导入 | ✅ | 前端按钮触发URL导入；后端 `POST /api/v1/rag/documents/import-url` 抓取+解析+索引 |
| P4-4 | 文档解析增强 | ✅ | PDF表格检测→Markdown表格转换；OCR支持(PaddleOCR/Tesseract)；`load_file_with_ocr()` 图片提取 |
| P4-5 | 增量索引管道 | ✅ | 新建 `src/rag/indexing_pipeline.py`：`IncrementalIndexer` 定时扫描/MD5变化检测/自动增量更新；完整REST API管理 |
| P4-6 | 前端对话接入 RAG | ✅ | ChatView调用真实API（RAG模式/Agent模式切换）；inline citation `[1]` 高亮渲染；来源文档统计展示 |

---

## P5 — 工程化与评估

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| P5-1 | RAG 全链路追踪 | ✅ | 新建 `src/monitoring/rag_tracer.py`：TraceSpan/RAGTrace 延迟追踪；集成到search()全步骤(p50/p95)；`GET /api/v1/rag/trace/stats` + `/recent` |
| P5-2 | RAGAS 评估体系 | ✅ | 新建 `src/rag/ragas_eval.py`：RAGASEvaluator 四级指标(faithfulness/relevance/precision/context_recall)；简单词重叠+LLM精确评估；`POST /api/v1/rag/eval/run` |
| P5-3 | 语义缓存 | ✅ | 新建 `src/rag/semantic_cache.py`：SemanticCache Redis/Local双层缓存；`GET /api/v1/rag/cache/stats` + `POST /invalidate`；集成到search() |
| P5-4 | 文档权限控制 | ✅ | RAGService新增 `set_acl()`/`check_access()`；`POST /api/v1/rag/acl` 设置readers/writers；`GET` 查看 |
| P5-5 | 用户反馈闭环 | ✅ | `POST /api/v1/rag/feedback`：rating+feedback记录审计日志；关联skill_id自动更新成功率 |

---

## M — 多模态文档理解 (NEW)

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| M-1 | Docling PDF解析 | ✅ | `document_loader.py`：Docling优先（MIT协议，结构化markdown+表格），PyMuPDF兜底；`_render_page_images()`页面截图 |
| M-2 | 视觉检索模块 | ✅ | 新建 `src/rag/visual_indexer.py`：CLIP(CPU可跑)/ColQwen2(GPU可选)/感知hash三级自动切换；页面→Milvus visual collection |
| M-3 | 多模态生成适配 | ✅ | `answer_question_multimodal()`；页面图片可在sources中引用，多模态LLM调用已预留 |
| M-4 | 混合检索集成 | ✅ | search()新增visual第四路检索源，4路RRF融合(vector+KG+sparse+visual)；`GET /api/v1/rag/visual/status` |
| M-5 | 零GPU可运行 | ✅ | 全链路支持CPU：CLIP ViT-B/32 (CPU) → Docling CPU模式 → 文本生成；GPU仅用于ColQwen2加速 |

---

## 进度概览

```
P0 基础联通     [4/4]  ████████████████████  100%
P1 意图路由     [4/4]  ████████████████████  100%
P2 检索质量     [7/7]  ████████████████████  100%
P3 答案质量     [4/4]  ████████████████████  100%
P4 前端与数据   [6/6]  ████████████████████  100%
P5 工程化       [5/5]  ████████████████████  100%
M  多模态       [5/5]  ████████████████████  100%
────────────────────────────────────────────
总计          [35/35] ████████████████████  100%
```

## 建议执行顺序

```
P0 (基础联通) → P1 (意图路由) → P2 (检索质量) → P3 (答案质量) → P4 (前端) → P5 (工程化)
```
