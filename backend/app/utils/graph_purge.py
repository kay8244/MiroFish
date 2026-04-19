"""group_id 범위의 모든 노드/엣지 purge.

파이프라인 resume 경로에서 실패한 run의 graph를 완전 삭제할 때 사용. Zep Cloud의
`client.graph.delete(graph_id=...)` 대체품. Neo4j DETACH DELETE는 엣지까지
함께 제거하므로 별도 정리 불필요.
"""

from __future__ import annotations

from .logger import get_logger

logger = get_logger('mirofish.graph_purge')


def purge_group(
    driver,
    group_id: str,
    database: str = 'neo4j',
    batch_size: int = 1000,
) -> dict[str, int]:
    """group_id에 속한 모든 Entity 노드 + 연결된 엣지 제거.

    매우 큰 그래프를 대비해 batch로 나눠 삭제한다 (트랜잭션 락 분산). 대부분의
    MiroFish run은 ~100 nodes 수준이라 단일 배치로 끝난다.

    Returns:
        {'nodes_deleted': int, 'relationships_deleted': int}
    """
    total_nodes = 0
    total_rels = 0
    with driver.session(database=database) as session:
        while True:
            summary = session.run(
                """
                MATCH (n:Entity)
                WHERE n.group_id = $gid
                WITH n LIMIT $batch
                DETACH DELETE n
                RETURN count(n) AS nodes
                """,
                gid=group_id,
                batch=batch_size,
            ).single()
            deleted = summary['nodes'] if summary else 0
            if deleted == 0:
                break
            total_nodes += deleted

        # Episodic 노드도 있으면 같이 제거 (add_episode가 만든 보조 노드).
        ep_summary = session.run(
            """
            MATCH (n:Episodic)
            WHERE n.group_id = $gid
            DETACH DELETE n
            RETURN count(n) AS nodes
            """,
            gid=group_id,
        ).single()
        ep_deleted = ep_summary['nodes'] if ep_summary else 0
        total_nodes += ep_deleted

        # 관계는 DETACH DELETE로 같이 지워지지만, 별도 카운트가 필요하면 추가 쿼리.
        # Phase 1에서는 노드 카운트만 반환. Phase 6에서 필요 시 정교화.

    logger.info(
        f'graph purge: group_id={group_id}, nodes_deleted={total_nodes}'
    )
    return {'nodes_deleted': total_nodes, 'relationships_deleted': total_rels}
