"""
Graphiti/Neo4j 기반 엔티티 읽기 서비스 (Phase 3).

`ZepEntityReader`와 동일한 public API를 제공하되, 백엔드는 Graphiti(Neo4j)로
교체. 호출부(simulation.py, simulation_manager.py, oasis_profile_generator.py
등) 수정 없이 `services/__init__` alias 전환만으로 대체 가능하게 한다.

구현 전략:
- `utils.graphiti_paging`의 Cypher 헬퍼에 위임
- 페이징 dict → Zep-shape dict로 얇은 매핑 (키 이름 동일, 메타 필드 제거)
- 순수 필터/enrich 로직은 기존 ZepEntityReader와 동일
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..utils.graphiti_client import neo4j_driver
from ..utils.graphiti_paging import (
    fetch_all_edges,
    fetch_all_nodes,
    get_entity_edges,
    get_node_by_uuid,
)
from ..utils.logger import get_logger

logger = get_logger('mirofish.graphiti_entity_reader')

# attributes dict에서 제외할 Neo4j 메타 필드 (zep shape에서는 별도 필드로 노출됨)
_META_ATTR_KEYS = {"uuid", "name", "group_id", "labels", "summary", "created_at"}


@dataclass
class EntityNode:
    """엔티티 노드 데이터 구조 (ZepEntityReader 호환)."""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        for label in self.labels:
            if label not in ("Entity", "Node"):
                return label
        return None


@dataclass
class FilteredEntities:
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


def _map_node_to_zep_shape(raw: Dict[str, Any]) -> Dict[str, Any]:
    """graphiti_paging node dict → Zep-shape dict."""
    attrs = dict(raw.get("attributes") or {})
    for k in _META_ATTR_KEYS:
        attrs.pop(k, None)
    return {
        "uuid": raw.get("uuid") or "",
        "name": raw.get("name") or "",
        "labels": list(raw.get("labels") or []),
        "summary": raw.get("summary") or "",
        "attributes": attrs,
    }


def _map_edge_to_zep_shape(raw: Dict[str, Any]) -> Dict[str, Any]:
    """graphiti_paging edge dict → Zep-shape dict."""
    attrs = {
        k: v for k, v in raw.items()
        if k not in {"uuid", "name", "fact", "source_node_uuid",
                     "target_node_uuid", "other_node_uuid", "other_node_name"}
    }
    return {
        "uuid": raw.get("uuid") or "",
        "name": raw.get("name") or "",
        "fact": raw.get("fact") or "",
        "source_node_uuid": raw.get("source_node_uuid"),
        "target_node_uuid": raw.get("target_node_uuid"),
        "attributes": attrs,
    }


class GraphitiEntityReader:
    """
    Graphiti/Neo4j 엔티티 읽기 서비스 (ZepEntityReader 호환 API).

    driver 주입 가능 (테스트용). 기본은 `graphiti_client.neo4j_driver()`.
    """

    def __init__(self, driver=None, api_key: Optional[str] = None):
        # api_key 인자는 하위 호환용(실제 사용 안 함). ZepEntityReader 시그니처
        # 동일 유지를 위해 받아둠.
        _ = api_key
        self._driver = driver if driver is not None else neo4j_driver()
        self._owns_driver = driver is None

    def close(self) -> None:
        if self._owns_driver and self._driver is not None:
            try:
                self._driver.close()
            except Exception:  # noqa: BLE001
                pass
            self._driver = None

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"그래프 {graph_id}의 모든 노드 가져오는 중...")
        raw_nodes = fetch_all_nodes(self._driver, group_id=graph_id)
        nodes = [_map_node_to_zep_shape(n) for n in raw_nodes]
        logger.info(f"총 {len(nodes)}개 노드 가져옴")
        return nodes

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"그래프 {graph_id}의 모든 엣지 가져오는 중...")
        raw_edges = fetch_all_edges(self._driver, group_id=graph_id)
        edges = [_map_edge_to_zep_shape(e) for e in raw_edges]
        logger.info(f"총 {len(edges)}개 엣지 가져옴")
        return edges

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        try:
            raw = get_entity_edges(self._driver, node_uuid=node_uuid)
            return [_map_edge_to_zep_shape(e) for e in raw]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"노드 {node_uuid}의 엣지 가져오기 실패: {e}")
            return []

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        logger.info(f"그래프 {graph_id}의 엔티티 필터링 시작...")

        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        node_map = {n["uuid"]: n for n in all_nodes}

        filtered_entities: List[EntityNode] = []
        entity_types_found: Set[str] = set()

        for node in all_nodes:
            labels = node.get("labels", [])
            custom_labels = [l for l in labels if l not in ("Entity", "Node")]
            if not custom_labels:
                continue

            if defined_entity_types:
                matching = [l for l in custom_labels if l in defined_entity_types]
                if not matching:
                    continue
                entity_type = matching[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )

            if enrich_with_edges:
                related_edges: List[Dict[str, Any]] = []
                related_node_uuids: Set[str] = set()
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges

                related_nodes: List[Dict[str, Any]] = []
                for ruuid in related_node_uuids:
                    if ruuid in node_map:
                        rn = node_map[ruuid]
                        related_nodes.append({
                            "uuid": rn["uuid"],
                            "name": rn["name"],
                            "labels": rn["labels"],
                            "summary": rn.get("summary", ""),
                        })
                entity.related_nodes = related_nodes

            filtered_entities.append(entity)

        logger.info(
            f"필터링 완료: 전체 {total_count}, 충족 {len(filtered_entities)}, "
            f"유형: {entity_types_found}"
        )
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self, graph_id: str, entity_uuid: str
    ) -> Optional[EntityNode]:
        try:
            raw = get_node_by_uuid(self._driver, node_uuid=entity_uuid)
            if not raw:
                return None
            mapped = _map_node_to_zep_shape(raw)

            edges = self.get_node_edges(entity_uuid)
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}

            related_edges: List[Dict[str, Any]] = []
            related_node_uuids: Set[str] = set()
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])

            related_nodes: List[Dict[str, Any]] = []
            for ruuid in related_node_uuids:
                if ruuid in node_map:
                    rn = node_map[ruuid]
                    related_nodes.append({
                        "uuid": rn["uuid"],
                        "name": rn["name"],
                        "labels": rn["labels"],
                        "summary": rn.get("summary", ""),
                    })

            return EntityNode(
                uuid=mapped["uuid"],
                name=mapped["name"],
                labels=mapped["labels"],
                summary=mapped["summary"],
                attributes=mapped["attributes"],
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"엔티티 {entity_uuid} 가져오기 실패: {e}")
            return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> List[EntityNode]:
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities
