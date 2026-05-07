"""
Knowledge Graph Retriever
知识图谱检索器 — 基于 Neo4j 的实体关联检索
"""

from typing import List, Dict, Any, Optional
from datetime import datetime


class KnowledgeGraphRetriever:
    """基于Neo4j的知识图谱检索器"""

    def __init__(self, config: dict, neo4j_manager, llm_client=None):
        self.config = config
        self.neo4j = neo4j_manager
        self.llm = llm_client
        self.top_k = config.get('top_k_graph', 10)
        self._initialized = False

    async def initialize(self):
        self._initialized = True
        print("[KGRetriever] Initialized")
        # 建立索引约束
        await self.neo4j.create_entity('SystemIndex', {
            'id': 'kg_index',
            'name': 'knowledge_graph_root',
            'created_at': datetime.now().isoformat()
        })

    async def index_entities(self, entities: List[Dict[str, Any]]):
        """批量构建知识图谱实体"""
        for entity in entities:
            label = entity.get('label', 'Entity')
            await self.neo4j.create_entity(label, entity)

        print(f"[KGRetriever] Indexed {len(entities)} entities")

    async def index_relations(self, relations: List[Dict[str, Any]]):
        """批量构建实体关系"""
        for rel in relations:
            await self.neo4j.create_relation(
                from_id=rel['from'],
                to_id=rel['to'],
                relation_type=rel.get('type', 'RELATED_TO'),
                properties=rel.get('properties', {})
            )
        print(f"[KGRetriever] Indexed {len(relations)} relations")

    async def extract_and_index(
        self,
        doc_id: str,
        text: str,
        entities: List[Dict] = None,
        relations: List[Dict] = None
    ):
        """从文档提取实体关系并索引到知识图谱"""
        if entities is None:
            if self.llm:
                entities, relations = await self._extract_by_llm(doc_id, text)
            else:
                entities = self._extract_entities_from_text(doc_id, text)
        if relations is None:
            relations = self._extract_relations_from_text(doc_id, text, entities)

        if entities:
            await self.index_entities(entities)
        if relations:
            await self.index_relations(relations)

    def _extract_entities_from_text(self, doc_id: str, text: str) -> List[Dict]:
        """基于规则从文本提取实体（生产环境应使用NER模型）"""
        import re
        entities = []

        # 提取文档实体
        entities.append({
            'id': doc_id,
            'label': 'Document',
            'name': doc_id,
            'text_preview': text[:200]
        })

        # 提取关键词作为实体（简化实现：提取大写缩写、中文专有名词模式）
        abbreviations = re.findall(r'\b[A-Z]{2,}\b', text)
        for abbr in set(abbreviations[:5]):
            entities.append({
                'id': f"{doc_id}_abbr_{abbr}",
                'label': 'Concept',
                'name': abbr,
                'source_doc': doc_id
            })

        # 提取中文引号内的术语
        quoted = re.findall(r'[「『（(]([^」』）)]{2,20})[」』）)]', text)
        for term in set(quoted[:5]):
            entities.append({
                'id': f"{doc_id}_term_{hash(term) % 100000}",
                'label': 'Term',
                'name': term,
                'source_doc': doc_id
            })

        return entities

    async def _extract_by_llm(
        self, doc_id: str, text: str
    ) -> tuple:
        """LLM 驱动的实体关系抽取"""
        import json
        snippet = text[:3000]
        system_prompt = """你是信息抽取专家。从文档文本中提取实体和关系。

输出JSON格式：
{
  "entities": [{"id": "entity_id", "label": "Person/Organization/Concept/Term/Document", "name": "实体名"}, ...],
  "relations": [{"from": "entity_id_1", "to": "entity_id_2", "type": "RELATED_TO/CONTAINS/PART_OF/DEPENDS_ON", "properties": {}}, ...]
}"""

        try:
            response = await self.llm.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"文档ID: {doc_id}\n文本：{snippet}"}
            ], temperature=0.2)

            json_match = __import__('re').search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                entities = data.get('entities', [])
                relations = data.get('relations', [])
                print(f"[KGRetriever] LLM extracted {len(entities)} entities, "
                      f"{len(relations)} relations")
                return entities, relations
        except Exception as e:
            print(f"[KGRetriever] LLM extraction failed: {e}")

        return [], []

    def _extract_relations_from_text(
        self,
        doc_id: str,
        text: str,
        entities: List[Dict]
    ) -> List[Dict]:
        """基于规则提取实体间关系"""
        relations = []
        doc_entity_id = doc_id

        for entity in entities:
            if entity['id'] != doc_entity_id:
                relations.append({
                    'from': doc_entity_id,
                    'to': entity['id'],
                    'type': 'CONTAINS',
                    'properties': {'source': 'auto_extraction'}
                })

        return relations

    async def search_by_semantic(
        self,
        query: str,
        entity_types: List[str] = None,
        depth: int = 2,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """语义搜索知识图谱"""
        keyword_results = await self.neo4j.search_by_keyword(
            query, labels=entity_types, limit=limit
        )

        expanded_results = []
        for entity in keyword_results[:5]:
            entity_id = entity.get('id')
            if entity_id:
                paths = await self.neo4j.expand_from_entity(
                    entity_id,
                    depth=depth,
                    limit=5
                )
                expanded_results.extend(paths)

        return {
            'direct_matches': keyword_results,
            'expanded_paths': expanded_results,
            'total_matches': len(keyword_results)
        }

    async def get_entity_context(self, entity_id: str, depth: int = 2) -> Dict:
        """获取实体的上下文关联"""
        paths = await self.neo4j.expand_from_entity(entity_id, depth=depth, limit=20)
        entity_info = await self.neo4j.query_entity('Entity', {'id': entity_id})

        return {
            'entity': entity_info[0] if entity_info else None,
            'relations': paths
        }

    def _clean_kg_results(self, raw: dict) -> List[Dict[str, Any]]:
        """清洗图检索结果为统一格式"""
        results = []

        for match in raw.get('direct_matches', []):
            results.append({
                'source': 'knowledge_graph',
                'type': 'entity',
                'entity': match.get('name', match.get('id', '')),
                'label': match.get('label', ''),
                'properties': {
                    k: v for k, v in match.items()
                    if k not in ('id', 'name', 'label')
                }
            })

        for path in raw.get('expanded_paths', []):
            for edge in path.get('edges', []):
                results.append({
                    'source': 'knowledge_graph',
                    'type': 'relation',
                    'relation_type': edge.get('type', ''),
                    'path': edge
                })

        return results
