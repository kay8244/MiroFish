"""Graphiti/Neo4j 그래프 노드·엣지 페이지 읽기 유틸리티.

Phase 3의 entity_reader/zep_tools 리팩토 이전에 쓸 수 있는 얇은 래퍼. Cypher로
`group_id` 스코프의 모든 노드/엣지를 skip/limit 페이징으로 반환한다. 반환 레코드는
dict 형태 (uuid/name/group_id/labels/attributes) — 기존 Zep SDK의 node/edge
객체와 API는 다르지만, 호출자가 속성 접근 방식만 바꾸면 된다.

기존 utils/zep_paging.py는 Phase 6에서 삭제된다.
"""

from __future__ import annotations

from typing import Any, Optional

from .logger import get_logger

logger = get_logger('mirofish.graphiti_paging')

_DEFAULT_PAGE_SIZE = 200
_MAX_NODES = 5000
_MAX_EDGES = 10000


def fetch_all_nodes(
    driver,
    group_id: str,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_items: int = _MAX_NODES,
    database: str = 'neo4j',
) -> list[dict[str, Any]]:
    """group_id 범위의 모든 Entity 노드를 dict 리스트로 반환.

    Graphiti는 노드에 `:Entity` 라벨을 부여하고 `group_id` 속성으로 네임스페이스
    구분한다. 반환 dict는 uuid/name/group_id/labels/attributes/summary/created_at.
    """
    all_nodes: list[dict[str, Any]] = []
    offset = 0
    with driver.session(database=database) as session:
        while len(all_nodes) < max_items:
            page = session.run(
                """
                MATCH (n:Entity)
                WHERE n.group_id = $gid
                RETURN
                    n.uuid AS uuid,
                    n.name AS name,
                    n.group_id AS group_id,
                    n.created_at AS created_at,
                    n.summary AS summary,
                    labels(n) AS labels,
                    properties(n) AS attributes
                ORDER BY n.uuid
                SKIP $skip LIMIT $limit
                """,
                gid=group_id,
                skip=offset,
                limit=page_size,
            ).data()
            if not page:
                break
            all_nodes.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

    if len(all_nodes) >= max_items:
        logger.warning(
            f'node count 상한 도달 ({max_items}), group_id={group_id} paging 중단'
        )
    return all_nodes[:max_items]


def fetch_all_edges(
    driver,
    group_id: str,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_items: int = _MAX_EDGES,
    database: str = 'neo4j',
) -> list[dict[str, Any]]:
    """group_id 범위의 모든 RELATES_TO 엣지를 dict 리스트로 반환.

    반환 dict는 uuid/name/fact/source_node_uuid/target_node_uuid/group_id/
    valid_at/invalid_at/created_at/episodes.
    """
    all_edges: list[dict[str, Any]] = []
    offset = 0
    with driver.session(database=database) as session:
        while len(all_edges) < max_items:
            page = session.run(
                """
                MATCH (s:Entity)-[e:RELATES_TO]->(t:Entity)
                WHERE e.group_id = $gid
                RETURN
                    e.uuid AS uuid,
                    e.name AS name,
                    e.fact AS fact,
                    s.uuid AS source_node_uuid,
                    t.uuid AS target_node_uuid,
                    e.group_id AS group_id,
                    e.valid_at AS valid_at,
                    e.invalid_at AS invalid_at,
                    e.created_at AS created_at,
                    e.episodes AS episodes
                ORDER BY e.uuid
                SKIP $skip LIMIT $limit
                """,
                gid=group_id,
                skip=offset,
                limit=page_size,
            ).data()
            if not page:
                break
            all_edges.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

    if len(all_edges) >= max_items:
        logger.warning(
            f'edge count 상한 도달 ({max_items}), group_id={group_id} paging 중단'
        )
    return all_edges[:max_items]


def get_node_by_uuid(
    driver,
    node_uuid: str,
    database: str = 'neo4j',
) -> Optional[dict[str, Any]]:
    """UUID로 단일 노드 조회. Graphiti는 built-in lookup API가 없어 직접 Cypher 사용."""
    with driver.session(database=database) as session:
        rec = session.run(
            """
            MATCH (n:Entity {uuid: $uuid})
            RETURN
                n.uuid AS uuid,
                n.name AS name,
                n.group_id AS group_id,
                n.created_at AS created_at,
                n.summary AS summary,
                labels(n) AS labels,
                properties(n) AS attributes
            LIMIT 1
            """,
            uuid=node_uuid,
        ).single()
        return rec.data() if rec else None


def get_entity_edges(
    driver,
    node_uuid: str,
    database: str = 'neo4j',
    max_items: int = 1000,
) -> list[dict[str, Any]]:
    """특정 노드에 연결된 모든 엣지를 반환 (방향 무관)."""
    with driver.session(database=database) as session:
        return session.run(
            """
            MATCH (n:Entity {uuid: $uuid})-[e:RELATES_TO]-(m:Entity)
            RETURN
                e.uuid AS uuid,
                e.name AS name,
                e.fact AS fact,
                startNode(e).uuid AS source_node_uuid,
                endNode(e).uuid AS target_node_uuid,
                m.uuid AS other_node_uuid,
                m.name AS other_node_name,
                e.group_id AS group_id,
                e.created_at AS created_at
            LIMIT $limit
            """,
            uuid=node_uuid,
            limit=max_items,
        ).data()
