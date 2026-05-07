"""
Neo4j Knowledge Graph Manager
Neo4j知识图谱管理器 — 实体关系存储与图检索
"""

from typing import List, Dict, Any, Optional
from datetime import datetime


class Neo4jManager:
    """Neo4j图数据库管理器"""

    def __init__(self, config: dict):
        self.config = config
        self.uri = config.get('uri', 'bolt://localhost:7687')
        self.user = config.get('user', 'neo4j')
        self.password = config.get('password', 'password')
        self.database = config.get('database', 'neo4j')
        self._driver = None
        self._connected = False
        self._mock_store: Dict[str, list] = {
            'nodes': [],
            'edges': []
        }

    async def connect(self):
        """连接Neo4j"""
        try:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            await self._driver.verify_connectivity()
            self._connected = True
            print(f"[Neo4j] Connected to {self.uri}")
        except ImportError:
            print("[Neo4j] neo4j driver not installed, using mock mode")
        except Exception as e:
            print(f"[Neo4j] Connection failed: {e}, using mock mode")

    async def create_entity(self, label: str, properties: Dict[str, Any]) -> str:
        """创建实体节点"""
        entity_id = properties.get('id') or f"{label}_{datetime.now().timestamp()}"
        properties['created_at'] = datetime.now().isoformat()

        if self._driver and self._connected:
            try:
                async with self._driver.session(database=self.database) as session:
                    result = await session.run(
                        f"MERGE (n:{label} {{id: $id}}) SET n += $props RETURN n.id as id",
                        id=entity_id, props=properties
                    )
                    record = await result.single()
                    return record['id'] if record else entity_id
            except Exception as e:
                print(f"[Neo4j] Create entity failed: {e}")

        self._mock_store['nodes'].append({'label': label, **properties})
        return entity_id

    async def create_relation(
        self,
        from_id: str,
        to_id: str,
        relation_type: str,
        properties: Dict[str, Any] = None
    ):
        """创建实体间关系"""
        props = properties or {}
        props['created_at'] = datetime.now().isoformat()

        if self._driver and self._connected:
            try:
                async with self._driver.session(database=self.database) as session:
                    await session.run(
                        f"""
                        MATCH (a {{id: $from_id}}), (b {{id: $to_id}})
                        MERGE (a)-[r:{relation_type}]->(b)
                        SET r += $props
                        """,
                        from_id=from_id, to_id=to_id, props=props
                    )
                    return
            except Exception as e:
                print(f"[Neo4j] Create relation failed: {e}")

        self._mock_store['edges'].append({
            'from': from_id, 'to': to_id,
            'type': relation_type, 'properties': props
        })

    async def query_entity(self, label: str, properties: Dict[str, Any] = None) -> List[Dict]:
        """查询实体"""
        props = properties or {}

        if self._driver and self._connected:
            try:
                conditions = " AND ".join([f"n.{k} = ${k}" for k in props])
                where_clause = f"WHERE {conditions}" if conditions else ""
                async with self._driver.session(database=self.database) as session:
                    result = await session.run(
                        f"MATCH (n:{label}) {where_clause} RETURN n",
                        **props
                    )
                    return [record['n'] async for record in result]
            except Exception as e:
                print(f"[Neo4j] Query entity failed: {e}")

        matching = []
        for node in self._mock_store['nodes']:
            if node.get('label') == label:
                if all(node.get(k) == v for k, v in props.items()):
                    matching.append(node)
        return matching

    async def expand_from_entity(
        self,
        entity_id: str,
        relation_types: List[str] = None,
        depth: int = 2,
        limit: int = 50
    ) -> List[Dict]:
        """从实体出发扩展关联实体和关系"""
        if self._driver and self._connected:
            try:
                rel_filter = ""
                if relation_types:
                    types = "|".join(relation_types)
                    rel_filter = f"WHERE all(r in relationships(p) WHERE type(r) in ['{types}'])"

                async with self._driver.session(database=self.database) as session:
                    result = await session.run(
                        f"""
                        MATCH path = (start {{id: $entity_id}})-[*1..{depth}]-(related)
                        {rel_filter}
                        RETURN path LIMIT $limit
                        """,
                        entity_id=entity_id, limit=limit
                    )
                    paths = []
                    async for record in result:
                        path_data = {'nodes': [], 'edges': []}
                        for node in record['path'].nodes:
                            path_data['nodes'].append(dict(node))
                        for rel in record['path'].relationships:
                            path_data['edges'].append({
                                'type': type(rel).__name__,
                                'from': rel.start_node['id'],
                                'to': rel.end_node['id'],
                                'properties': dict(rel)
                            })
                        paths.append(path_data)
                    return paths
            except Exception as e:
                print(f"[Neo4j] Expand entity failed: {e}")

        return self._mock_expand(entity_id, depth, limit)

    def _mock_expand(self, entity_id: str, depth: int, limit: int) -> list:
        """Mock图扩展查询"""
        visited = {entity_id}
        frontier = {entity_id}
        result_nodes = []
        result_edges = []

        for _ in range(depth):
            new_frontier = set()
            for node_id in frontier:
                for node in self._mock_store['nodes']:
                    if node.get('id') == node_id and node not in result_nodes:
                        result_nodes.append(node)
            for edge in self._mock_store['edges']:
                if edge['from'] in frontier and edge['to'] not in visited:
                    result_edges.append(edge)
                    new_frontier.add(edge['to'])
                    visited.add(edge['to'])
                elif edge['to'] in frontier and edge['from'] not in visited:
                    result_edges.append(edge)
                    new_frontier.add(edge['from'])
                    visited.add(edge['from'])
            frontier = new_frontier
            if not frontier:
                break

        return [{'nodes': result_nodes, 'edges': result_edges}] if result_nodes else []

    async def search_by_keyword(
        self,
        keyword: str,
        labels: List[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """关键词搜索实体"""
        label_filter = "|".join(labels) if labels else ""

        if self._driver and self._connected:
            try:
                label_clause = f"AND (any(l in labels(n) WHERE l in ['{label_filter}']))" if label_filter else ""
                async with self._driver.session(database=self.database) as session:
                    result = await session.run(
                        f"""
                        MATCH (n)
                        WHERE (
                            n.text CONTAINS $keyword OR
                            n.name CONTAINS $keyword OR
                            n.title CONTAINS $keyword
                        ) {label_clause}
                        RETURN n LIMIT $limit
                        """,
                        keyword=keyword, limit=limit
                    )
                    return [record['n'] async for record in result]
            except Exception as e:
                print(f"[Neo4j] Keyword search failed: {e}")

        results = []
        for node in self._mock_store['nodes']:
            node_str = str(node).lower()
            if keyword.lower() in node_str:
                if not labels or node.get('label') in labels:
                    results.append(node)
        return results[:limit]

    async def close(self):
        """关闭连接"""
        if self._driver:
            await self._driver.close()
            self._connected = False
        print("[Neo4j] Connection closed")


_neo4j_instance: Optional[Neo4jManager] = None


def get_neo4j(config: dict) -> Neo4jManager:
    global _neo4j_instance
    if _neo4j_instance is None:
        _neo4j_instance = Neo4jManager(config)
    return _neo4j_instance
