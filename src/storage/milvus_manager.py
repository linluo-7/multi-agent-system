"""
Milvus Vector Storage Manager
Milvus向量存储管理器 — 支持文本向量化存储与相似度检索
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime


class MilvusManager:
    """Milvus向量数据库管理器"""

    def __init__(self, config: dict):
        self.config = config
        self.host = config.get('host', 'localhost')
        self.port = config.get('port', 19530)
        self.collection_name = config.get('collection', 'multi_agent_memory')
        self.dim = config.get('dim', 1024)
        self._connected = False
        self._collections = {}
        self._mock_store: Dict[str, list] = {}
        self._collections = {}

    async def connect(self):
        """连接Milvus服务"""
        try:
            from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType

            connections.connect(
                alias="default",
                host=self.host,
                port=self.port
            )
            self._connected = True
            print(f"[Milvus] Connected to {self.host}:{self.port}")
        except ImportError:
            print("[Milvus] pymilvus not installed, using mock mode")
        except Exception as e:
            print(f"[Milvus] Connection failed: {e}, using mock mode")

    async def create_collection(self, name: str, dim: int = None) -> bool:
        """创建向量集合"""
        dim = dim or self.dim
        try:
            from pymilvus import Collection, FieldSchema, CollectionSchema, DataType

            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema(name="metadata", dtype=DataType.JSON),
                FieldSchema(name="created_at", dtype=DataType.INT64),
            ]
            schema = CollectionSchema(fields, description=f"Collection: {name}")
            collection = Collection(name=name, schema=schema)

            index_params = {
                "metric_type": "IP",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024}
            }
            collection.create_index(field_name="embedding", index_params=index_params)
            collection.load()

            self._collections[name] = collection
            print(f"[Milvus] Collection '{name}' created (dim={dim})")
            return True
        except Exception as e:
            print(f"[Milvus] Failed to create collection '{name}': {e}")
            return False

    async def get_or_create_collection(self, name: str) -> Any:
        """获取或创建集合"""
        if name in self._collections:
            return self._collections[name]

        try:
            from pymilvus import Collection
            collection = Collection(name=name)
            collection.load()
            self._collections[name] = collection
            return collection
        except Exception:
            await self.create_collection(name)
            return self._collections.get(name)

    async def insert(self, collection_name: str, vectors: List[Dict[str, Any]]) -> bool:
        """批量插入向量数据"""
        collection = await self.get_or_create_collection(collection_name)
        if collection is None:
            self._mock_store.setdefault(collection_name, [])
            for v in vectors:
                self._mock_store[collection_name].append(v)
            return True

        try:
            entities = [
                [v.get('id') for v in vectors],
                [v.get('text', '') for v in vectors],
                [v.get('embedding', []) for v in vectors],
                [v.get('metadata', {}) for v in vectors],
                [int(v.get('timestamp', datetime.now().timestamp())) for v in vectors],
            ]
            collection.insert(entities)
            collection.flush()
            return True
        except Exception as e:
            print(f"[Milvus] Insert failed: {e}")
            return False

    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 5,
        filter_expr: str = None
    ) -> List[Dict[str, Any]]:
        """向量相似度搜索"""
        collection = await self.get_or_create_collection(collection_name)
        if collection is None:
            results = self._mock_search(collection_name, query_vector, top_k)
            return results

        try:
            search_params = {"metric_type": "IP", "params": {"nprobe": 16}}
            results = collection.search(
                data=[query_vector],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=filter_expr,
                output_fields=["id", "text", "metadata", "created_at"]
            )

            formatted = []
            for hits in results:
                for hit in hits:
                    formatted.append({
                        'id': hit.id,
                        'text': hit.entity.get('text', ''),
                        'score': float(hit.score),
                        'metadata': hit.entity.get('metadata', {}),
                        'created_at': hit.entity.get('created_at')
                    })
            return formatted
        except Exception as e:
            print(f"[Milvus] Search failed: {e}")
            return self._mock_search(collection_name, query_vector, top_k)

    async def delete_by_ids(self, collection_name: str, ids: List[str]) -> bool:
        """按ID删除向量"""
        collection = await self.get_or_create_collection(collection_name)
        if collection is None:
            return True
        try:
            collection.delete(f"id in {ids}")
            return True
        except Exception as e:
            print(f"[Milvus] Delete failed: {e}")
            return False

    async def close(self):
        """关闭连接"""
        if self._connected:
            try:
                from pymilvus import connections
                connections.disconnect("default")
            except Exception:
                pass
            self._connected = False
        print("[Milvus] Connection closed")

    # 内嵌轻量 mock 用于开发/离线场景
    _mock_store: Dict[str, list] = {}

    def _mock_search(self, collection_name: str, query_vector: list, top_k: int) -> list:
        """Mock搜索 - 基于简单的余弦相似度"""
        import math

        def dot(a, b):
            return sum(x * y for x, y in zip(a, b))

        def norm(a):
            return math.sqrt(sum(x * x for x in a))

        def cosine(a, b):
            na, nb = norm(a), norm(b)
            return dot(a, b) / (na * nb) if na and nb else 0.0

        stored = self._mock_store.get(collection_name, [])
        scored = []
        for item in stored:
            emb = item.get('embedding', [])
            if emb:
                score = cosine(query_vector, emb)
                scored.append({**item, 'score': score})

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:top_k]


_milvus_instance: Optional[MilvusManager] = None


def get_milvus(config: dict) -> MilvusManager:
    global _milvus_instance
    if _milvus_instance is None:
        _milvus_instance = MilvusManager(config)
    return _milvus_instance
