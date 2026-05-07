"""
RAG Pipeline Tracer
RAG全链路追踪 — 延迟/命中率/LLM token消耗埋点
"""
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TraceSpan:
    """单步骤追踪"""
    name: str
    start_time: float
    end_time: float = 0
    duration_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finish(self, **meta):
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.metadata.update(meta)


@dataclass
class RAGTrace:
    """一次完整RAG请求的全链路追踪"""
    trace_id: str
    query: str
    kb_name: str
    start_time: float
    end_time: float = 0
    total_ms: float = 0
    spans: List[TraceSpan] = field(default_factory=list)

    # 汇总指标
    vector_latency_ms: float = 0
    kg_latency_ms: float = 0
    sparse_latency_ms: float = 0
    fusion_latency_ms: float = 0
    rerank_latency_ms: float = 0
    llm_latency_ms: float = 0
    llm_tokens: int = 0
    total_hits: int = 0
    max_score: float = 0
    avg_score: float = 0
    fallback_triggered: bool = False

    def finish(self, results: Dict = None):
        self.end_time = time.time()
        self.total_ms = round((self.end_time - self.start_time) * 1000, 2)
        if results:
            self.total_hits = results.get('total_found', 0)
            scores = [r.get('score', 0) for r in results.get('results', [])]
            self.max_score = max(scores) if scores else 0
            self.avg_score = round(sum(scores) / len(scores), 3) if scores else 0

    def span(self, name: str) -> TraceSpan:
        span = TraceSpan(name=name, start_time=time.time())
        self.spans.append(span)
        return span

    def to_dict(self) -> dict:
        return {
            'trace_id': self.trace_id,
            'query': self.query[:100],
            'kb_name': self.kb_name,
            'total_ms': self.total_ms,
            'vector_ms': self.vector_latency_ms,
            'kg_ms': self.kg_latency_ms,
            'sparse_ms': self.sparse_latency_ms,
            'fusion_ms': self.fusion_latency_ms,
            'rerank_ms': self.rerank_latency_ms,
            'llm_ms': self.llm_latency_ms,
            'llm_tokens': self.llm_tokens,
            'total_hits': self.total_hits,
            'max_score': self.max_score,
            'avg_score': self.avg_score,
            'fallback': self.fallback_triggered,
            'spans': [{'name': s.name, 'ms': s.duration_ms, **s.metadata}
                      for s in self.spans],
            'timestamp': datetime.now().isoformat()
        }


class RAGTracer:
    """RAG链路追踪器"""

    def __init__(self, redis_manager=None, metrics_collector=None):
        self.redis = redis_manager
        self.metrics = metrics_collector
        self._recent_traces: List[RAGTrace] = []
        self._max_recent = 100

    def start_trace(self, query: str, kb_name: str = 'default') -> RAGTrace:
        import uuid
        trace = RAGTrace(
            trace_id=str(uuid.uuid4())[:12],
            query=query,
            kb_name=kb_name,
            start_time=time.time()
        )
        return trace

    def record_trace(self, trace: RAGTrace):
        """记录追踪数据"""
        self._recent_traces.append(trace)
        if len(self._recent_traces) > self._max_recent:
            self._recent_traces = self._recent_traces[-self._max_recent:]

        # 写入Redis（最近1000条）
        if self.redis:
            try:
                key = f"mas:rag_traces"
                self.redis.redis.lpush(key, str(trace.to_dict()))
                self.redis.redis.ltrim(key, 0, 999)
            except Exception:
                pass

        # Prometheus指标
        if self.metrics:
            try:
                self.metrics.observe_rag_latency(trace.total_ms)
                self.metrics.observe_rag_hits(trace.total_hits)
            except Exception:
                pass

    def get_stats(self) -> dict:
        """聚合统计"""
        if not self._recent_traces:
            return {'total_requests': 0}

        traces = self._recent_traces
        latencies = [t.total_ms for t in traces]
        hits = [t.total_hits for t in traces]
        scores = [t.max_score for t in traces if t.max_score > 0]
        fallback_rate = sum(1 for t in traces if t.fallback_triggered) / len(traces)

        return {
            'total_requests': len(traces),
            'avg_latency_ms': round(sum(latencies) / len(latencies), 1),
            'p50_latency_ms': round(sorted(latencies)[len(latencies)//2], 1),
            'p95_latency_ms': round(sorted(latencies)[int(len(latencies)*0.95)], 1),
            'avg_hits': round(sum(hits) / len(hits), 1) if hits else 0,
            'avg_max_score': round(sum(scores) / len(scores), 3) if scores else 0,
            'fallback_rate': round(fallback_rate, 3),
            'kb_stats': self._kb_stats(traces)
        }

    def _kb_stats(self, traces: List[RAGTrace]) -> dict:
        stats = {}
        for t in traces:
            if t.kb_name not in stats:
                stats[t.kb_name] = {'requests': 0, 'avg_hits': 0, 'avg_ms': 0}
            stats[t.kb_name]['requests'] += 1
            stats[t.kb_name]['avg_hits'] += t.total_hits
            stats[t.kb_name]['avg_ms'] += t.total_ms
        for k in stats:
            n = stats[k]['requests']
            stats[k]['avg_hits'] = round(stats[k]['avg_hits'] / n, 1)
            stats[k]['avg_ms'] = round(stats[k]['avg_ms'] / n, 1)
        return stats

    def get_recent_traces(self, limit: int = 20) -> List[dict]:
        return [t.to_dict() for t in self._recent_traces[-limit:]]
