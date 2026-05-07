"""
Intent Classifier
意图分类器 — 关键词 + LLM 两级分类，决定任务分发目标
"""
import json
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class IntentResult:
    intent: str  # rag / search / code / doc / reasoning / mixed
    confidence: float  # 0.0 ~ 1.0
    sub_intents: List[str] = field(default_factory=list)
    suggested_agents: List[str] = field(default_factory=list)
    kb_name: Optional[str] = None
    reasoning: str = ""


# -------- 关键词规则库 --------

INTENT_KEYWORDS: Dict[str, List[str]] = {
    'rag': [
        '知识库', '内部文档', '根据文档', '资料库', '合同', '手册',
        '产品说明', '制度', '政策', '规章', '规范', '条款',
        'rag', 'knowledge base', 'internal document', 'reference',
        '查阅资料', '内部资料', '公司规定', '技术文档',
    ],
    'search': [
        '搜索', '查找', '查询', '了解', '知道', '最新', '新闻',
        '网上', '网络', '互联网', '百度', '谷歌',
        'search', 'find', 'look up', 'what is', 'who is', 'when',
        'news', 'latest', 'current', 'trending',
    ],
    'code': [
        '代码', '编程', '写程序', '执行', '运行', '调试', 'bug',
        '错误', '报错', '实现', '函数', '类', '脚本', '自动化',
        'code', 'program', 'run', 'execute', 'debug', 'fix',
        'implement', 'function', 'class', 'script', 'python',
        'javascript', 'java', 'golang', 'rust',
    ],
    'doc': [
        '文档', '报告', '生成', '导出', '写文章', '总结', '概括',
        '整理', '格式化', 'word', 'pdf', 'markdown', 'ppt',
        'doc', 'report', 'generate', 'write', 'summarize', 'format',
    ],
}


KB_NAME_KEYWORDS: Dict[str, List[str]] = {
    'default': ['一般', '通用', '默认'],
    'tech': ['技术', '代码', '架构', 'API', '接口'],
    'product': ['产品', '功能', '特性', '规格'],
    'policy': ['制度', '政策', '规章', '规定', '合规', '法务'],
}


def classify_by_keywords(user_input: str) -> IntentResult:
    """基于关键词规则的意图分类"""
    user_lower = user_input.lower()
    scores: Dict[str, int] = {}

    for intent, keywords in INTENT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in user_lower:
                score += 1
        scores[intent] = score

    # 找出最匹配
    max_score = max(scores.values()) if scores else 0
    if max_score == 0:
        return IntentResult(
            intent='search',
            confidence=0.3,
            suggested_agents=['search'],
            reasoning='无明确关键词匹配，默认搜索'
        )

    primary = max(scores, key=scores.get)
    secondary = [k for k, v in scores.items() if v > 0 and k != primary]

    # 置信度计算
    total_kw = sum(scores.values())
    confidence = min(0.9, 0.4 + max_score / (total_kw + 1) * 0.5)

    is_mixed = len(secondary) > 0 and max(scores.values()) <= sum(
        v for k, v in scores.items() if k != primary) + 1

    sub_intents = [primary] + secondary if is_mixed else []
    suggested_agents = [primary] if not is_mixed else [primary] + secondary[:1]

    # 推测知识库
    kb_name = _infer_kb_name(user_lower)

    return IntentResult(
        intent='mixed' if is_mixed else primary,
        confidence=confidence,
        sub_intents=sub_intents,
        suggested_agents=suggested_agents,
        kb_name=kb_name,
        reasoning=f'关键词匹配: primary={primary} score={max_score}'
    )


def _infer_kb_name(user_lower: str) -> Optional[str]:
    """根据用户输入推测目标知识库"""
    for kb_name, keywords in KB_NAME_KEYWORDS.items():
        for kw in keywords:
            if kw in user_lower:
                return kb_name
    return None


async def classify_by_llm(user_input: str, llm_client) -> IntentResult:
    """基于 LLM 的意图分类（更高精度）"""
    if llm_client is None:
        return classify_by_keywords(user_input)

    system_prompt = """你是多Agent协作系统的意图分类专家。分析用户输入，判断需要哪些Agent处理。

可用Agent:
- rag: 知识库文档检索（内部文档、合同、手册、规章制度）
- search: 网络搜索（最新信息、事实查询、趋势）
- code: 代码编写和执行
- doc: 文档生成和格式化
- reasoning: 逻辑校验

输出格式（JSON）:
{
  "primary": "主要需要的Agent",
  "secondary": ["次要Agent"],
  "confidence": 0.85,
  "kb_name": "知识库名或null",
  "reasoning": "简短分析"
}"""

    try:
        response = await llm_client.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户输入：{user_input}"}
        ], temperature=0.1)

        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            primary = data.get('primary', 'search')
            secondary = data.get('secondary', [])
            suggested = [primary] + secondary
            return IntentResult(
                intent='mixed' if secondary else primary,
                confidence=float(data.get('confidence', 0.8)),
                sub_intents=[primary] + secondary if secondary else [],
                suggested_agents=suggested[:3],
                kb_name=data.get('kb_name'),
                reasoning=data.get('reasoning', 'LLM分类')
            )
    except Exception as e:
        print(f"[IntentClassifier] LLM classification failed: {e}")

    return classify_by_keywords(user_input)


class IntentClassifier:
    """意图分类器，优先 LLM，fallback 关键词"""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def classify(self, user_input: str) -> IntentResult:
        if self.llm:
            return await classify_by_llm(user_input, self.llm)
        return classify_by_keywords(user_input)

    def classify_sync(self, user_input: str) -> IntentResult:
        return classify_by_keywords(user_input)
