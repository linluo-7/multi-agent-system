"""
Embedding Service
中文Embedding向量化服务 — 支持文本批量向量化
"""

import asyncio
import hashlib
import re
from typing import List, Optional
from functools import lru_cache


class EmbeddingService:
    """文本向量化服务"""

    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get('model', 'BAAI/bge-large-zh-v1.5')
        self.device = config.get('device', 'cpu')
        self.batch_size = config.get('batch_size', 32)
        self.max_length = config.get('max_length', 512)
        self._model = None
        self._dim = config.get('dim', 1024)

    async def initialize(self):
        """加载模型"""
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._dim = self._model.get_sentence_embedding_dimension()
            print(f"[Embedding] Model '{self.model_name}' loaded, dim={self._dim}")
        except ImportError:
            print("[Embedding] sentence-transformers not installed, using hash-based mock embeddings")
        except Exception as e:
            print(f"[Embedding] Model load failed: {e}, using mock")

    @property
    def dim(self) -> int:
        return self._dim

    async def encode(self, texts: List[str]) -> List[List[float]]:
        """批量文本向量化"""
        if not texts:
            return []

        cleaned = [self._preprocess(t) for t in texts]

        if self._model is not None:
            try:
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(
                    None,
                    lambda: self._model.encode(
                        cleaned,
                        batch_size=self.batch_size,
                        show_progress_bar=False,
                        normalize_embeddings=True
                    )
                )
                return embeddings.tolist()
            except Exception as e:
                print(f"[Embedding] Encode failed: {e}")

        return [self._mock_embed(t) for t in cleaned]

    async def encode_single(self, text: str) -> List[float]:
        """单文本向量化"""
        results = await self.encode([text])
        return results[0] if results else self._mock_embed(text)

    def _mock_embed(self, text: str) -> List[float]:
        """Mock embedding: 基于文本哈希生成模拟向量（1024维）"""
        import math
        hash_bytes = hashlib.sha256(text.encode('utf-8')).digest()
        vec = []
        for i in range(self._dim):
            byte_val = hash_bytes[i % len(hash_bytes)]
            angle = (byte_val / 255.0) * 2 * math.pi + (i * 0.01)
            vec.append(math.sin(angle) * 0.1)
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm > 0 else vec

    def _preprocess(self, text: str) -> str:
        """文本预处理"""
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        if len(text) > self.max_length:
            text = text[:self.max_length]
        return text

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """文本分块，支持滑动窗口重叠"""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]

            if end < len(text):
                last_period = max(chunk.rfind('。'), chunk.rfind('.'), chunk.rfind('\n'))
                if last_period > chunk_size // 2:
                    end = start + last_period + 1

            chunks.append(text[start:end].strip())
            start = end - overlap

        return chunks


_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service(config: dict) -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(config)
    return _embedding_service
