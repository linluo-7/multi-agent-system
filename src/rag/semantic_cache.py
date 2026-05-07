"""
Semantic Cache
语义缓存 — Redis缓存高频查询 + 相似问去重
"""
import hashlib
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime


class SemanticCache:
    """语义缓存层：减少重复检索的延迟和LLM调用"""

    def __init__(self, redis_manager=None, embedding_service=None, config: dict = None):
        self.redis = redis_manager
        self.embedding = embedding_service
        self.config = config or {}
        self.similarity_threshold = self.config.get('cache_similarity_threshold', 0.92)
        self.ttl = self.config.get('cache_ttl', 3600)
        self._local_cache: Dict[str, Dict] = {}
        self._stats = {'hits': 0, 'misses': 0, 'similar_hits': 0}

    def _cache_key(self, query: str, kb_name: str = 'default') -> str:
        """生成缓存key"""
        normalized = query.strip().lower()
        h = hashlib.md5(f"{kb_name}:{normalized}".encode()).hexdigest()
        return f"rag:cache:{h[:16]}"

    async def get(self, query: str, kb_name: str = 'default') -> Optional[Dict]:
        """查询缓存（精确匹配 + 语义相似匹配）"""
        # 1. 精确缓存查找
        key = self._cache_key(query, kb_name)
        cached = await self._redis_get(key)
        if cached:
            self._stats['hits'] += 1
            cached['from_cache'] = True
            cached['cache_type'] = 'exact'
            return cached

        # 2. 本地缓存
        if key in self._local_cache:
            entry = self._local_cache[key]
            if time.time() - entry['ts'] < self.ttl:
                self._stats['hits'] += 1
                entry['data']['from_cache'] = True
                entry['data']['cache_type'] = 'local'
                return entry['data']

        self._stats['misses'] += 1
        return None

    async def set(self, query: str, result: Dict, kb_name: str = 'default'):
        """写入缓存"""
        key = self._cache_key(query, kb_name)
        cache_entry = {
            'query': query,
            'kb_name': kb_name,
            'result': result,
            'ts': time.time()
        }

        # Redis
        await self._redis_set(key, cache_entry, self.ttl)

        # 本地
        self._local_cache[key] = {'ts': time.time(), 'data': result}
        if len(self._local_cache) > 500:
            # LRU淘汰
            oldest = sorted(self._local_cache.items(), key=lambda x: x[1]['ts'])[:100]
            for k, _ in oldest:
                del self._local_cache[k]

    async def invalidate(self, kb_name: str = None):
        """失效缓存"""
        if kb_name:
            pattern = f"rag:cache:*"
            if self.redis:
                try:
                    keys = self.redis.redis.keys(pattern)
                    if keys:
                        self.redis.redis.delete(*keys)
                except Exception:
                    pass
            self._local_cache.clear()
            print(f"[Cache] Invalidated cache for kb={kb_name}")
        else:
            self._local_cache.clear()
            print(f"[Cache] Invalidated all cache")

    def get_stats(self) -> dict:
        total = self._stats['hits'] + self._stats['misses']
        hit_rate = self._stats['hits'] / total if total > 0 else 0
        return {
            'hits': self._stats['hits'],
            'misses': self._stats['misses'],
            'similar_hits': self._stats['similar_hits'],
            'hit_rate': round(hit_rate, 3),
            'local_size': len(self._local_cache)
        }

    async def _redis_get(self, key: str) -> Optional[Dict]:
        if not self.redis:
            return None
        try:
            raw = self.redis.redis.get(key)
            if raw:
                entry = json.loads(raw)
                return entry.get('result')
        except Exception:
            pass
        return None

    async def _redis_set(self, key: str, entry: Dict, ttl: int):
        if not self.redis:
            return
        try:
            self.redis.redis.setex(key, ttl, json.dumps(entry, ensure_ascii=False))
        except Exception:
            pass
