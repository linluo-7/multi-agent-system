"""
RAGAS Evaluation
RAG质量评估 — faithfulness / relevance / precision 自动化评估
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EvalResult:
    """单次评估结果"""
    query: str
    answer: str
    faithfulness: float   # 答案是否忠于检索文档
    relevance: float      # 检索文档是否与问题相关
    precision: float      # 检索精度
    context_recall: float  # 上下文召回率
    overall: float        # 综合分数
    details: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class RAGASEvaluator:
    """RAGAS 评估器"""

    def __init__(self, llm_client=None):
        self.llm = llm_client
        self._eval_history: List[EvalResult] = []

    def evaluate_simple(
        self, query: str, answer: str, contexts: List[str],
        sources: List[Dict]
    ) -> EvalResult:
        """简单指标评估（无需LLM）"""
        # Relevance: 上下文与query的简单重叠
        relevance = self._compute_relevance(query, contexts)

        # Precision: 检索结果中有多少是相关的
        precision = self._compute_precision(query, contexts)

        # Context recall: 答案中使用了多少检索到的信息
        context_recall = self._compute_context_recall(answer, contexts)

        # Faithfulness: 答案内容有多少来自检索文档
        faithfulness = self._compute_faithfulness_simple(answer, contexts)

        overall = (faithfulness * 0.35 + relevance * 0.25 +
                   precision * 0.20 + context_recall * 0.20)

        result = EvalResult(
            query=query, answer=answer[:500],
            faithfulness=round(faithfulness, 3),
            relevance=round(relevance, 3),
            precision=round(precision, 3),
            context_recall=round(context_recall, 3),
            overall=round(overall, 3),
            details={'sources_count': len(sources), 'contexts_chars': sum(len(c) for c in contexts)}
        )
        self._eval_history.append(result)
        return result

    async def evaluate_llm(
        self, query: str, answer: str, contexts: List[str],
        sources: List[Dict]
    ) -> Optional[EvalResult]:
        """LLM 驱动的精确评估"""
        if not self.llm:
            return self.evaluate_simple(query, answer, contexts, sources)

        try:
            from ..monitoring.rag_tracer import RAGTracer
        except ImportError:
            pass

        # Faithfulness 评估
        faithfulness = await self._eval_faithfulness(answer, contexts)
        relevance = self._compute_relevance(query, contexts)
        precision = self._compute_precision(query, contexts)
        context_recall = self._compute_context_recall(answer, contexts)

        overall = (faithfulness * 0.35 + relevance * 0.25 +
                   precision * 0.20 + context_recall * 0.20)

        result = EvalResult(
            query=query, answer=answer[:500],
            faithfulness=round(faithfulness, 3),
            relevance=round(relevance, 3),
            precision=round(precision, 3),
            context_recall=round(context_recall, 3),
            overall=round(overall, 3),
            details={'sources_count': len(sources), 'eval_mode': 'llm'}
        )
        self._eval_history.append(result)
        return result

    async def _eval_faithfulness(self, answer: str, contexts: List[str]) -> float:
        """LLM评估答案忠实度"""
        import json
        ctx = '\n---\n'.join(contexts[:3])[:2000]
        prompt = f"""评估以下答案是否完全基于提供的文档内容，是否有编造信息。

文档内容：
{ctx}

答案：
{answer[:1000]}

输出JSON: {{"score": 0.85, "hallucinations": ["编造的内容片段"], "reason": "评估理由"}}"""

        try:
            resp = await self.llm.ainvoke([{"role": "user", "content": prompt}], temperature=0.1)
            m = __import__('re').search(r'\{.*\}', resp, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return float(data.get('score', 0.5))
        except Exception:
            pass
        return 0.5

    def _compute_relevance(self, query: str, contexts: List[str]) -> float:
        """计算查询与上下文的相关性（词重叠）"""
        import re
        q_tokens = set(re.findall(r'[\w一-鿿]{2,}', query.lower()))
        if not q_tokens:
            return 0.0
        scores = []
        for ctx in contexts[:5]:
            ctx_tokens = set(re.findall(r'[\w一-鿿]{2,}', ctx.lower()))
            overlap = len(q_tokens & ctx_tokens)
            scores.append(min(1.0, overlap / len(q_tokens)))
        return sum(scores) / len(scores) if scores else 0.0

    def _compute_precision(self, query: str, contexts: List[str]) -> float:
        """检索精度：检索到的文档中有多少相关"""
        if not contexts:
            return 0.0
        scores = [self._compute_relevance(query, [c]) for c in contexts[:5]]
        return sum(scores) / len(scores) if scores else 0.0

    def _compute_context_recall(self, answer: str, contexts: List[str]) -> float:
        """上下文召回率：答案中有多少信息来自检索文档"""
        import re
        a_tokens = set(re.findall(r'[\w一-鿿]{2,}', answer.lower()))
        if not a_tokens:
            return 0.0
        all_ctx_tokens = set()
        for ctx in contexts[:5]:
            all_ctx_tokens.update(re.findall(r'[\w一-鿿]{2,}', ctx.lower()))
        overlap = len(a_tokens & all_ctx_tokens)
        return min(1.0, overlap / len(a_tokens))

    def _compute_faithfulness_simple(self, answer: str, contexts: List[str]) -> float:
        """简单忠实度：答案词在上下文中的覆盖率"""
        import re
        a_tokens = set(re.findall(r'[\w一-鿿]{2,}', answer.lower()))
        if not a_tokens:
            return 0.0
        all_ctx = '\n'.join(contexts).lower()
        covered = sum(1 for t in a_tokens if t in all_ctx)
        return covered / len(a_tokens) if a_tokens else 0.0

    def get_stats(self) -> dict:
        if not self._eval_history:
            return {'total_evals': 0}
        recent = self._eval_history[-100:]
        return {
            'total_evals': len(self._eval_history),
            'avg_faithfulness': round(sum(e.faithfulness for e in recent) / len(recent), 3),
            'avg_relevance': round(sum(e.relevance for e in recent) / len(recent), 3),
            'avg_precision': round(sum(e.precision for e in recent) / len(recent), 3),
            'avg_overall': round(sum(e.overall for e in recent) / len(recent), 3),
        }
