"""
Sparse Retriever (BM25)
稀疏检索器 — 基于 BM25 的关键词检索，与 Dense 向量检索互补
"""
import math
import re
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict


class BM25Scorer:
    """轻量级 BM25 实现"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_freq: Dict[str, int] = defaultdict(int)  # DF per term
        self.doc_lengths: List[int] = []
        self.avg_dl: float = 0
        self.total_docs: int = 0

    def tokenize(self, text: str) -> List[str]:
        """中英文分词"""
        # 英文小写 + 分词
        text = text.lower()
        tokens = []
        # 匹配中文字符、英文单词、数字
        for match in re.finditer(r'[一-鿿]+|[a-zA-Z]+|\d+', text):
            token = match.group()
            if len(token) >= 2:  # 过滤单字
                tokens.append(token)
        # 对中文做 bigram
        chinese_tokens = []
        for tok in tokens:
            if re.match(r'[一-鿿]+', tok) and len(tok) >= 2:
                for i in range(len(tok) - 1):
                    chinese_tokens.append(tok[i:i + 2])
                if len(tok) >= 3:
                    chinese_tokens.append(tok)  # 全词也保留
            else:
                chinese_tokens.append(tok)
        return chinese_tokens

    def index(self, documents: List[Dict[str, str]]):
        """批量索引文档"""
        self.total_docs = 0
        self.doc_freq.clear()
        self.doc_lengths = []

        for doc in documents:
            self.add_document(doc.get('text', ''))

    def add_document(self, text: str):
        """索引单个文档"""
        tokens = self.tokenize(text)
        self.doc_lengths.append(len(tokens))
        self.total_docs += 1

        seen = set()
        for token in tokens:
            if token not in seen:
                self.doc_freq[token] += 1
                seen.add(token)

        if self.total_docs > 0:
            self.avg_dl = sum(self.doc_lengths) / self.total_docs

    def score(self, query: str, doc_text: str) -> float:
        """计算 BM25 分数"""
        query_tokens = self.tokenize(query)
        doc_tokens = self.tokenize(doc_text)
        doc_len = len(doc_tokens)

        if doc_len == 0 or self.total_docs == 0:
            return 0.0

        score = 0.0
        term_freq = defaultdict(int)
        for t in doc_tokens:
            term_freq[t] += 1

        for token in query_tokens:
            df = self.doc_freq.get(token, 0)
            if df == 0:
                continue

            idf = math.log(1 + (self.total_docs - df + 0.5) / (df + 0.5))
            tf = term_freq.get(token, 0)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_dl)
            score += idf * numerator / denominator

        return score


class SparseRetriever:
    """稀疏检索器，与 Dense 向量检索互补"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.scorer = BM25Scorer(
            k1=self.config.get('bm25_k1', 1.5),
            b=self.config.get('bm25_b', 0.75)
        )
        self._docs: Dict[str, Dict] = {}

    def index_document(self, doc_id: str, text: str, metadata: dict = None):
        """索引文档"""
        self._docs[doc_id] = {'id': doc_id, 'text': text, 'metadata': metadata or {}}
        self.scorer.add_document(text)

    def index_documents(self, docs: List[Dict[str, Any]]):
        """批量索引"""
        for doc in docs:
            self.index_document(
                doc.get('id', str(hash(doc.get('text', '')))),
                doc.get('text', doc.get('content', '')),
                doc.get('metadata', {})
            )

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_doc_ids: List[str] = None
    ) -> List[Dict[str, Any]]:
        """BM25 检索"""
        results = []
        for doc_id, doc in self._docs.items():
            if filter_doc_ids and doc_id not in filter_doc_ids:
                continue
            bm25_score = self.scorer.score(query, doc['text'])
            if bm25_score > 0:
                results.append({
                    'id': doc_id,
                    'text': doc['text'][:500],
                    'score': bm25_score,
                    'source': 'bm25',
                    'metadata': doc.get('metadata', {})
                })

        # 按分数排序
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    def get_stats(self) -> dict:
        return {
            'total_docs': self.scorer.total_docs,
            'avg_doc_length': round(self.scorer.avg_dl, 1),
            'vocab_size': len(self.scorer.doc_freq)
        }
