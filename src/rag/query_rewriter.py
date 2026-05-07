"""
Query Rewriter
查询改写模块 — 多轮上下文改写 / HyDE / 子问题拆解
"""
import re
import json
from typing import Dict, List, Optional, Tuple


class QueryRewriter:
    """查询改写器，支持上下文消解、HyDE、子问题拆解"""

    def __init__(self, llm_client=None, config: dict = None):
        self.llm = llm_client
        self.config = config or {}
        self.hyde_enabled = self.config.get('hyde_enabled', True)
        self.decompose_enabled = self.config.get('decompose_enabled', True)

    # ---- 多轮对话上下文改写 ----

    def rewrite_with_context(
        self,
        query: str,
        history: List[Dict[str, str]],
        max_history: int = 4
    ) -> str:
        """基于对话历史改写query，消解指代和省略"""
        if not history:
            return query

        recent = history[-max_history * 2:]
        if not recent:
            return query

        context_parts = []
        for msg in recent:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            prefix = '用户' if role == 'user' else '系统'
            context_parts.append(f"{prefix}: {content[:200]}")

        rewritten = self._rewrite_rule_based(query, recent)
        return rewritten

    def _rewrite_rule_based(self, query: str, history: List[Dict]) -> str:
        """基于规则的多轮改写（无LLM时使用）"""

        # 指代消解：补充上一轮用户问题
        last_user = ''
        for msg in reversed(history):
            if msg.get('role') == 'user' and msg.get('content', '') != query:
                last_user = msg['content']
                break

        # 明显的指代词
        referential_patterns = [
            (r'^(它|他|她|这个|那个|这|那|其)\s*', 'referential'),
            (r'^(还有|另外|再|继续|接着|然后|此外)\s*', 'continuation'),
            (r'^(上面的|前面的|刚才的|之前)\s*', 'back_ref'),
        ]

        is_referential = any(
            re.match(p, query) for p, _ in referential_patterns
        )

        if is_referential and last_user:
            # 提取上一个问题的核心名词
            keywords = self._extract_keywords(last_user)
            if keywords:
                return f"{keywords} {query}"

        # 简短追问：拼接上一轮上下文
        if len(query) < 10 and last_user:
            return f"{last_user} — 追问：{query}"

        return query

    def _extract_keywords(self, text: str) -> str:
        """提取文本中的核心实体/关键词"""
        # 简单实现：提取中文名词短语
        patterns = [
            r'([一-鿿]{2,8}(?:系统|框架|模型|算法|方法|技术|方案|架构|平台|工具|服务|模式|策略|协议|标准|规范|接口|组件|模块|引擎|机制|流程|规则|配置|数据|文档|代码))',
            r'[「『"]([^」』"]{2,20})[」』"]',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                return ' '.join(matches[:3])
        return ''

    # ---- HyDE 假设文档生成 ----

    async def generate_hyde_document(self, query: str) -> Optional[str]:
        """生成HyDE假设文档，用作文本 embedding 查询"""
        if not self.llm or not self.hyde_enabled:
            return None

        prompt = f"""请根据以下问题，写一段假设性的文档段落（100-200字），
该段落像是从相关文档中摘录出来的，包含可能回答问题的关键信息。

问题：{query}

假设文档段落："""

        try:
            response = await self.llm.ainvoke([
                {"role": "user", "content": prompt}
            ], temperature=0.3)
            hyde_doc = response.strip()
            print(f"[QueryRewriter] HyDE generated: {len(hyde_doc)} chars")
            return hyde_doc
        except Exception as e:
            print(f"[QueryRewriter] HyDE generation failed: {e}")
            return None

    # ---- 子问题拆解 ----

    async def decompose_query(self, query: str) -> List[str]:
        """将复杂问题拆解为子问题"""
        if not self.decompose_enabled:
            return [query]

        if self.llm:
            return await self._decompose_by_llm(query)
        return self._decompose_rule_based(query)

    async def _decompose_by_llm(self, query: str) -> List[str]:
        """LLM 驱动的子问题拆解"""
        system_prompt = """将复杂问题拆解为2-5个子问题，每个子问题独立可检索。

输出JSON数组：
["子问题1", "子问题2"]

规则：
- 对比/比较类问题 → 拆成各自独立的问题
- 多条件复合问题 → 拆成单个条件的问题
- 简单单一问题 → 返回原问题"""

        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"问题：{query}"}
            ], temperature=0.2)

            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                sub_queries = json.loads(json_match.group())
                if isinstance(sub_queries, list) and len(sub_queries) > 0:
                    print(f"[QueryRewriter] Decomposed into {len(sub_queries)} sub-queries")
                    return sub_queries
        except Exception as e:
            print(f"[QueryRewriter] LLM decomposition failed: {e}")

        return self._decompose_rule_based(query)

    def _decompose_rule_based(self, query: str) -> List[str]:
        """基于规则的子问题拆解"""
        # 对比类
        compare_markers = ['vs', 'VS', '对比', '比较', '区别', '差异', '和', '与', '跟']
        for marker in compare_markers:
            parts = re.split(rf'\s*{marker}\s*', query, maxsplit=1)
            if len(parts) == 2 and len(parts[0]) > 3 and len(parts[1]) > 3:
                return [
                    f"{parts[0].strip()} 的特点和优势",
                    f"{parts[1].strip()} 的特点和优势",
                    f"{query} 的核心区别"
                ]

        # 并列问题
        sub_markers = ['；', ';', '？第二', '？第三', '？2.', '？3.']
        for marker in sub_markers:
            if marker in query:
                parts = re.split(r'[；;]|(?<=？)', query)
                parts = [p.strip() for p in parts if len(p.strip()) > 5]
                if len(parts) > 1:
                    return parts

        return [query]

    # ---- 综合改写入口 ----

    async def rewrite(
        self,
        query: str,
        history: List[Dict[str, str]] = None,
        use_hyde: bool = True,
        decompose: bool = False
    ) -> Dict[str, Any]:
        """综合查询改写入口"""
        result = {
            'original': query,
            'rewritten': query,
            'hyde_document': None,
            'sub_queries': [],
            'search_query': query,  # 实际用于检索的query
        }

        # 1. 上下文改写
        if history:
            result['rewritten'] = self.rewrite_with_context(query, history)
            result['search_query'] = result['rewritten']

        # 2. HyDE 生成
        if use_hyde and self.hyde_enabled:
            hyde_doc = await self.generate_hyde_document(result['rewritten'])
            if hyde_doc:
                result['hyde_document'] = hyde_doc
                # 用 HyDE 文档做检索查询（原始 query 保留用于 LLM 回答）
                result['search_query'] = hyde_doc

        # 3. 子问题拆解
        if decompose:
            result['sub_queries'] = await self.decompose_query(result['rewritten'])

        return result
