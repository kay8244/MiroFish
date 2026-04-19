"""Graphiti 기반 그래프 빌더 (Phase 2 도입 / Phase 6 canonical 승격).

Zep Cloud SDK 기반 구현은 `graph_builder_zep_legacy.py`로 이동. 기본 백엔드는
Graphiti(Neo4j). API 시그니처는 기존 `GraphBuilderService`를 그대로 유지.

호환 API (그대로 유지):
  - build_graph_async(text, ontology, graph_name, chunk_size, chunk_overlap,
      batch_size=unused_legacy_param) → task_id
  - TaskManager를 통한 progress 추적
  - 완료 시 반환 결과: {'graph_id', 'graph_info', 'chunks_processed'}

Graphiti 전환 핵심:
  - graph_id는 Graphiti `group_id`로 사용 (기존 Zep `graph_id`와 동일 네이밍 규칙
    `mirofish_<uuid16>`).
  - 별도 create_graph / set_ontology 호출 없음 — 첫 add_episode 시 자동 생성,
    entity_types/edge_types dict를 매 add_episode에 전달.
  - batch_size는 legacy 파라미터로 받되 무시. Graphiti는 SEMAPHORE_LIMIT(=10)로
    내부 동시성 제어.
  - _wait_for_episodes 폴링 루프 제거 — await add_episode가 완료 보장.
"""

from __future__ import annotations

import asyncio
import os
import threading
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from ..models.task import TaskManager, TaskStatus
from ..utils.graphiti_client import GraphitiConfig, create_graphiti, neo4j_driver
from ..utils.graphiti_paging import fetch_all_edges, fetch_all_nodes
from ..utils.logger import get_logger
from .text_processor import TextProcessor

logger = get_logger('mirofish.graph_builder')


_RESERVED_ATTR_NAMES = {
    'uuid', 'name', 'group_id', 'name_embedding',
    'summary', 'created_at', 'fact', 'fact_embedding',
}


def _safe_attr_name(attr_name: str) -> str:
    """Graphiti/Neo4j 예약 속성명 회피."""
    return f'entity_{attr_name}' if attr_name.lower() in _RESERVED_ATTR_NAMES else attr_name


def build_entity_types(ontology: Dict[str, Any]) -> Dict[str, type]:
    """온톨로지 dict에서 {name: pydantic class} 매핑 생성 (entity 전용)."""
    entity_types: Dict[str, type] = {}
    for entity_def in ontology.get('entity_types', []) or []:
        name = entity_def['name']
        description = entity_def.get('description') or f'A {name} entity.'

        attrs: Dict[str, Any] = {'__doc__': description}
        annotations: Dict[str, Any] = {}
        for attr_def in entity_def.get('attributes', []) or []:
            attr_name = _safe_attr_name(attr_def['name'])
            attr_desc = attr_def.get('description') or attr_name
            attrs[attr_name] = Field(default=None, description=attr_desc)
            annotations[attr_name] = Optional[str]
        attrs['__annotations__'] = annotations
        entity_class = type(name, (BaseModel,), attrs)
        entity_class.__doc__ = description
        entity_types[name] = entity_class
    return entity_types


def build_edge_types(ontology: Dict[str, Any]) -> Dict[str, type]:
    """온톨로지 dict에서 {name: pydantic class} 매핑 생성 (edge 전용).

    Graphiti는 edge source/target 제약을 별도 edge_type_map으로 받는다 (선택적).
    현재 build은 edge attribute만 매핑하고, source_targets 제약은 LLM이 자연어
    context로 판단하도록 둔다. Phase 3 이후 필요 시 edge_type_map 추가.
    """
    edge_types: Dict[str, type] = {}
    for edge_def in ontology.get('edge_types', []) or []:
        name = edge_def['name']
        description = edge_def.get('description') or f'A {name} relationship.'

        attrs: Dict[str, Any] = {'__doc__': description}
        annotations: Dict[str, Any] = {}
        for attr_def in edge_def.get('attributes', []) or []:
            attr_name = _safe_attr_name(attr_def['name'])
            attr_desc = attr_def.get('description') or attr_name
            attrs[attr_name] = Field(default=None, description=attr_desc)
            annotations[attr_name] = Optional[str]
        attrs['__annotations__'] = annotations
        edge_class = type(name, (BaseModel,), attrs)
        edge_class.__doc__ = description
        edge_types[name] = edge_class
    return edge_types


@dataclass
class GraphInfo:
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'graph_id': self.graph_id,
            'node_count': self.node_count,
            'edge_count': self.edge_count,
            'entity_types': self.entity_types,
        }


class GraphBuilderService:
    """Graphiti + Neo4j 기반 그래프 빌더 (canonical)."""

    def __init__(self, graphiti_config: Optional[GraphitiConfig] = None):
        self.graphiti_config = graphiti_config or GraphitiConfig.from_env()
        self.task_manager = TaskManager()

    # ── 공개 API (legacy 호환) ─────────────────────────────────

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = 'MiroFish Graph',
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3,  # legacy, ignored
    ) -> str:
        """비동기 그래프 구축 시작. 호출 즉시 task_id 반환."""
        task_id = self.task_manager.create_task(
            task_type='graph_build',
            metadata={
                'graph_name': graph_name,
                'chunk_size': chunk_size,
                'text_length': len(text),
                'backend': 'graphiti',
            },
        )
        t = threading.Thread(
            target=self._worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap),
            name=f'graph-build-{task_id[:8]}',
            daemon=True,
        )
        t.start()
        return task_id

    # ── 내부 구현 ─────────────────────────────────────────────

    def _worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        """TaskManager thread worker. asyncio 루프는 여기서 띄운다."""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message='Graphiti 그래프 구축 시작...',
            )
            result = asyncio.run(
                self._build_async(
                    task_id, text, ontology, graph_name, chunk_size, chunk_overlap
                )
            )
            self.task_manager.complete_task(task_id, result)
        except Exception as e:
            err = f'{type(e).__name__}: {e}\n{traceback.format_exc()}'
            logger.error(f'graph build 실패 task_id={task_id}: {err}')
            self.task_manager.fail_task(task_id, err)

    async def _build_async(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> Dict[str, Any]:
        graph_id = f'mirofish_{uuid.uuid4().hex[:16]}'
        group_id = graph_id  # Graphiti namespace로 재사용
        logger.info(f'graph build 시작 group_id={group_id} name={graph_name!r}')

        self.task_manager.update_task(
            task_id, progress=10, message=f'group_id={group_id[:24]}...',
        )

        # 1) 온톨로지 → pydantic 클래스 dict
        # 참고: graphiti-core 0.11.x의 add_episode는 entity_types만 받는다.
        # edge는 LLM이 episode 본문에서 자동 추출하므로 edge_types는 보조 메타
        # (ontology_generator/tools 쪽에서만 쓸 수 있도록 build은 해두되 전달 X).
        entity_types = build_entity_types(ontology)
        edge_types = build_edge_types(ontology)
        logger.info(
            f'ontology build: entities={list(entity_types)}, '
            f'edges(meta only)={list(edge_types)}'
        )
        self.task_manager.update_task(
            task_id, progress=15,
            message=f'ontology: entity {len(entity_types)} + edge {len(edge_types)} (meta)',
        )

        # 2) 텍스트 청킹
        chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
        total = len(chunks)
        self.task_manager.update_task(
            task_id, progress=20,
            message=f'텍스트 {total}개 청크로 분할',
        )
        logger.info(f'chunks: {total} (chunk_size={chunk_size} overlap={chunk_overlap})')

        # 3) Graphiti 초기화
        graphiti = create_graphiti(self.graphiti_config)
        try:
            await graphiti.build_indices_and_constraints()

            # 4) 병렬 add_episode — outer semaphore로 동시 chunk 수 제한.
            #    Graphiti 내부 SEMAPHORE_LIMIT만으로는 부족 (각 add_episode가
            #    여러 nested LLM 호출을 가짐 → chunk 9개 × nested concurrent =
            #    조직 TPM 한도 200k 즉시 돌파). outer 제한으로 burst 평탄화.
            #    기본 2, GRAPH_BUILDER_MAX_CONCURRENT 환경변수로 조정 가능.
            max_concurrent = int(os.environ.get('GRAPH_BUILDER_MAX_CONCURRENT', '2'))
            # chunk 간 인위적 지연 — OpenAI 조직 TPM 한도(우리 환경 Tier 1 기준
            # 200k/min)가 9 chunks × ~35k tokens 동시 처리에 부족할 때 사용.
            # Tier 2+ 환경에서는 0으로 두면 최대 throughput.
            chunk_delay_s = float(os.environ.get('GRAPH_BUILDER_CHUNK_DELAY_S', '0'))
            outer_semaphore = asyncio.Semaphore(max_concurrent)
            reference_time = datetime.now(timezone.utc)
            completed = {'count': 0}
            lock = asyncio.Lock()

            async def add_one(idx: int, chunk: str) -> None:
                async with outer_semaphore:
                    await _add_one_unlocked(idx, chunk)
                    if chunk_delay_s > 0:
                        await asyncio.sleep(chunk_delay_s)

            async def _add_one_unlocked(idx: int, chunk: str) -> None:
                try:
                    # EpisodeType import는 버전 따라 위치가 달라 graceful fallback
                    source = None
                    try:
                        from graphiti_core.nodes import EpisodeType  # type: ignore
                        source = EpisodeType.text
                    except ImportError:
                        pass

                    kwargs = dict(
                        name=f'{graph_name} chunk {idx + 1}/{total}',
                        episode_body=chunk,
                        source_description='MiroFish seed chunk',
                        reference_time=reference_time,
                        group_id=group_id,
                        entity_types=entity_types,
                    )
                    if source is not None:
                        kwargs['source'] = source
                    # graphiti-core 0.11+ 버전에 따라 edge_types 파라미터 지원 여부가
                    # 다름. 지원 시 전달, 아니면 entity_types만 전달 (LLM이 edge 자동 추출).
                    try:
                        await graphiti.add_episode(**kwargs, edge_types=edge_types)
                    except TypeError:
                        await graphiti.add_episode(**kwargs)
                finally:
                    async with lock:
                        completed['count'] += 1
                        done = completed['count']
                    # 20 ~ 85% 범위에서 진행률 반영
                    if done % max(1, total // 10) == 0 or done == total:
                        self.task_manager.update_task(
                            task_id,
                            progress=20 + int(done / max(1, total) * 65),
                            message=f'add_episode {done}/{total}',
                        )

            await asyncio.gather(*[add_one(i, c) for i, c in enumerate(chunks)])

            # 5) 그래프 정보 수집 (노드/엣지 count, entity_types 실측)
            self.task_manager.update_task(
                task_id, progress=90, message='graph info 수집 중...',
            )
            info = self._collect_graph_info(group_id, expected_types=list(entity_types))
            logger.info(
                f'graph build 완료 group_id={group_id} '
                f'nodes={info.node_count} edges={info.edge_count}'
            )
            return {
                'graph_id': group_id,
                'graph_info': info.to_dict(),
                'chunks_processed': total,
            }
        finally:
            try:
                await graphiti.close()
            except Exception as e:
                logger.warning(f'graphiti.close 중 경고: {e}')

    def _collect_graph_info(
        self, group_id: str, expected_types: Optional[List[str]] = None
    ) -> GraphInfo:
        """Neo4j에서 그래프 요약 수집."""
        driver = neo4j_driver(self.graphiti_config)
        try:
            nodes = fetch_all_nodes(
                driver, group_id=group_id,
                database=self.graphiti_config.neo4j_database,
            )
            edges = fetch_all_edges(
                driver, group_id=group_id,
                database=self.graphiti_config.neo4j_database,
            )
            # 실측 entity_types: 노드의 labels - {'Entity'} (Graphiti가 Entity + 구체 label 부여)
            actual_labels: set[str] = set()
            for n in nodes:
                for label in n.get('labels') or []:
                    if label != 'Entity':
                        actual_labels.add(label)
            entity_list = sorted(actual_labels) or (expected_types or [])
            return GraphInfo(
                graph_id=group_id,
                node_count=len(nodes),
                edge_count=len(edges),
                entity_types=entity_list,
            )
        finally:
            driver.close()

    # ── 조회/삭제 API (api/graph.py 엔드포인트) ─────────────────────
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """그래프 시각화용 nodes/edges payload 반환. GraphPanel.vue에서 소비."""
        driver = neo4j_driver(self.graphiti_config)
        try:
            raw_nodes = fetch_all_nodes(
                driver, group_id=graph_id,
                database=self.graphiti_config.neo4j_database,
            )
            raw_edges = fetch_all_edges(
                driver, group_id=graph_id,
                database=self.graphiti_config.neo4j_database,
            )
        finally:
            driver.close()

        nodes = [
            {
                'uuid': n.get('uuid'),
                'name': n.get('name'),
                'labels': [lbl for lbl in (n.get('labels') or []) if lbl != 'Entity'],
                'summary': n.get('summary'),
                'attributes': n.get('attributes') or {},
                'created_at': n.get('created_at'),
            }
            for n in raw_nodes
        ]
        edges = [
            {
                'uuid': e.get('uuid'),
                'name': e.get('name'),
                'fact': e.get('fact'),
                'source_node_uuid': e.get('source_node_uuid'),
                'target_node_uuid': e.get('target_node_uuid'),
                'created_at': e.get('created_at'),
            }
            for e in raw_edges
        ]
        return {
            'graph_id': graph_id,
            'nodes': nodes,
            'edges': edges,
            'node_count': len(nodes),
            'edge_count': len(edges),
        }

    def delete_graph(self, graph_id: str) -> None:
        """group_id 범위의 모든 노드/엣지/에피소드를 Neo4j에서 제거."""
        driver = neo4j_driver(self.graphiti_config)
        try:
            with driver.session(database=self.graphiti_config.neo4j_database) as session:
                session.run(
                    """
                    MATCH (n)
                    WHERE n.group_id = $gid
                    DETACH DELETE n
                    """,
                    gid=graph_id,
                )
        finally:
            driver.close()
