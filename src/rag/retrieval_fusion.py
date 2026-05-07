"""
Retrieval Fusion
RRF倒数排名融合算法 — 融合多路检索结果
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """统一检索结果"""
    id: str
    text: str = ""
    score: float = 0.0
    source: str = ""  # vector / knowledge_graph / hybrid
    metadata: dict = field(default_factory=dict)
    highlight: str = ""


class RetrievalFusion:
    """多路检索结果融合排序"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.rrf_k = self.config.get('rrf_k', 60)
        self.fusion_top_k = self.config.get('fusion_top_k', 5)

    def rrf_fusion(
        self,
        result_groups: Dict[str, List[SearchResult]],
        top_k: int = None
    ) -> List[SearchResult]:
        """
        RRF (Reciprocal Rank Fusion) 算法融合多路检索结果

        公式: RRF(d) = sum(1 / (k + rank_i(d)))

        Args:
            result_groups: {'vector': [...], 'knowledge_graph': [...]}
            top_k: 返回top-k结果

        Returns:
            融合后的排序结果列表
        """
        top_k = top_k or self.fusion_top_k

        rrf_scores: Dict[str, float] = {}
        result_map: Dict[str, SearchResult] = {}

        for source, results in result_groups.items():
            for rank, result in enumerate(results, start=1):
                rid = result.id
                rrf_scores[rid] = rrf_scores.get(rid, 0.0) + 1.0 / (self.rrf_k + rank)

                if rid not in result_map:
                    result_map[rid] = result
                    result_map[rid].source = 'hybrid'
                else:
                    result_map[rid].score = max(result_map[rid].score, result.score)

        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        fused = []
        for rid in sorted_ids[:top_k]:
            result = result_map[rid]
            result.score = rrf_scores[rid]
            result.highlight = self._generate_highlight(result.text)
            fused.append(result)

        return fused

    def weighted_fusion(
        self,
        result_groups: Dict[str, List[SearchResult]],
        weights: Dict[str, float] = None,
        top_k: int = None
    ) -> List[SearchResult]:
        """
        加权融合：对不同检索源赋予不同权重

        Args:
            result_groups: 各检索源结果
            weights: 各检索源权重，默认 vector=0.6, kg=0.4
            top_k: 返回top-k
        """
        top_k = top_k or self.fusion_top_k
        weights = weights or {'vector': 0.6, 'knowledge_graph': 0.4}

        fused_scores: Dict[str, float] = {}
        result_map: Dict[str, SearchResult] = {}

        for source, results in result_groups.items():
            w = weights.get(source, 0.3)
            max_score = max((r.score for r in results), default=1.0)

            for rank, result in enumerate(results, start=1):
                rid = result.id
                normalized_score = result.score / max_score if max_score > 0 else 0
                position_score = 1.0 / rank
                weighted = w * normalized_score + (1 - w) * position_score

                fused_scores[rid] = fused_scores.get(rid, 0.0) + weighted
                if rid not in result_map:
                    result_map[rid] = result
                    result_map[rid].source = 'hybrid_weighted'

        sorted_ids = sorted(fused_scores.keys(), key=lambda x: fused_scores[x], reverse=True)

        fused = []
        for rid in sorted_ids[:top_k]:
            result = result_map[rid]
            result.score = fused_scores[rid]
            result.highlight = self._generate_highlight(result.text)
            fused.append(result)

        return fused

    async def rerank_by_llm(
        self,
        candidates: List[SearchResult],
        query: str,
        llm_client=None,
        top_n: int = None
    ) -> List[SearchResult]:
        """
        LLM / Cross-encoder 重排序

        Args:
            candidates: 融合后的候选结果
            query: 原始查询
            llm_client: LLM客户端
            top_n: 返回top-n
        """
        top_n = top_n or self.fusion_top_k
        if not candidates:
            return []
        if len(candidates) <= 1:
            return candidates[:top_n]

        if llm_client:
            return await self._llm_pointwise_rerank(candidates, query, llm_client, top_n)
        else:
            return self._diversity_rerank(candidates, query, top_n)

    async def _llm_pointwise_rerank(
        self, candidates: List[SearchResult], query: str, llm_client, top_n: int
    ) -> List[SearchResult]:
        """LLM pointwise 相关性打分"""
        import json
        docs_text = '\n\n'.join([
            f"[{i}] id={r.id[:20]}: {r.text[:200]}"
            for i, r in enumerate(candidates[:10])
        ])
        try:
            response = await llm_client.ainvoke([
                {"role": "system", "content": "你是一个文档相关性评估专家。对每个文档ID与查询的相关性打分(0-10分)，输出JSON数组：[{\"id\": \"开头字符\", \"score\": 8, \"reason\": \"理由\"}]"},
                {"role": "user", "content": f"查询：{query}\n\n候选文档：\n{docs_text}"}
            ], temperature=0.1)
            json_match = __import__('re').search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                scored = json.loads(json_match.group())
                score_map = {}
                for s in scored:
                    for c in candidates:
                        if c.id.startswith(s.get('id', '')[:8]):
                            score_map[c.id] = s.get('score', 5)
                            break
                for c in candidates:
                    llm_score = score_map.get(c.id, 5.0)
                    c.score = 0.5 * c.score + 0.5 * (llm_score / 10.0)
                print(f"[RetrievalFusion] LLM reranked {len(scored)}/{len(candidates)} candidates")
        except Exception as e:
            print(f"[RetrievalFusion] LLM rerank failed: {e}")

        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[:top_n]

    def _diversity_rerank(
        self, candidates: List[SearchResult], query: str, top_n: int
    ) -> List[SearchResult]:
        """多样性重排（MMR简化版）：按分数排序 + 内容去重"""
        seen_texts = set()
        reranked = []
        for r in sorted(candidates, key=lambda x: x.score, reverse=True):
            if len(reranked) >= top_n:
                break
            text_sig = r.text[:80]
            if text_sig not in seen_texts:
                seen_texts.add(text_sig)
                reranked.append(r)
        return reranked

    def deduplicate(self, results: List[SearchResult]) -> List[SearchResult]:
        """去重：保留每个ID得分最高的"""
        seen = {}
        for r in results:
            if r.id not in seen or r.score > seen[r.id].score:
                seen[r.id] = r
        return list(seen.values())

    def _generate_highlight(self, text: str, max_length: int = 150) -> str:
        """生成摘要高亮"""
        if not text:
            return ""
        if len(text) <= max_length:
            return text
        return text[:max_length].rsplit(' ', 1)[0].rsplit('\n', 1)[0] + '...'

    def format_for_llm(
        self,
        results: List[SearchResult],
        query: str,
        max_sources: int = 5
    ) -> str:
        """格式化检索结果为LLM可读的上下文"""
        if not results:
            return "（未找到相关文档）"

        parts = [f"检索查询：{query}\n"]
        parts.append(f"相关文档（共{len(results)}条）：\n")

        for i, r in enumerate(results[:max_sources], 1):
            source_name = r.metadata.get('filename', r.metadata.get('doc_id', r.source))
            parts.append(f"[{i}] 来源: {source_name}  |  相关度: {r.score:.3f}")
            parts.append(f"    {r.highlight}")
            parts.append("")

        return '\n'.join(parts)
