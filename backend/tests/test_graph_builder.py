"""
graph_builder pydantic 클래스 동적 생성 오프라인 테스트 (canonical Graphiti 구현).

live Graphiti/Neo4j 왕복은 graphiti_smoke_add_one.py와 smoke_rehearsal_v1.py로 검증.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pydantic import BaseModel  # noqa: E402

from app.services.graph_builder import (  # noqa: E402
    _safe_attr_name,
    build_edge_types,
    build_entity_types,
)


class TestSafeAttrName:
    def test_reserved_uuid_renamed(self):
        assert _safe_attr_name('uuid') == 'entity_uuid'

    def test_reserved_name_renamed(self):
        assert _safe_attr_name('name') == 'entity_name'

    def test_reserved_group_id_renamed(self):
        assert _safe_attr_name('group_id') == 'entity_group_id'

    def test_reserved_summary_renamed(self):
        assert _safe_attr_name('summary') == 'entity_summary'

    def test_case_insensitive(self):
        assert _safe_attr_name('UUID') == 'entity_UUID'
        assert _safe_attr_name('Name') == 'entity_Name'

    def test_normal_attribute_unchanged(self):
        assert _safe_attr_name('company_name') == 'company_name'
        assert _safe_attr_name('ticker') == 'ticker'


class TestBuildEntityTypes:
    def test_class_name_matches_definition(self):
        ontology = {
            'entity_types': [
                {'name': 'HyperScaler', 'description': 'Cloud provider'},
                {'name': 'Company', 'description': 'Generic company'},
            ]
        }
        entities = build_entity_types(ontology)
        assert set(entities.keys()) == {'HyperScaler', 'Company'}
        assert entities['HyperScaler'].__name__ == 'HyperScaler'
        assert issubclass(entities['HyperScaler'], BaseModel)

    def test_attributes_become_optional_str(self):
        ontology = {
            'entity_types': [
                {
                    'name': 'HyperScaler',
                    'description': '...',
                    'attributes': [
                        {'name': 'company_name', 'type': 'text',
                         'description': 'Official name'},
                        {'name': 'ticker', 'type': 'text', 'description': 'Ticker'},
                    ],
                }
            ]
        }
        cls = build_entity_types(ontology)['HyperScaler']
        instance = cls()
        assert instance.company_name is None
        assert instance.ticker is None
        instance2 = cls(company_name='Microsoft', ticker='MSFT')
        assert instance2.company_name == 'Microsoft'
        assert instance2.ticker == 'MSFT'

    def test_description_attached_as_docstring(self):
        ontology = {
            'entity_types': [
                {'name': 'HyperScaler', 'description': 'Cloud capex cycle'}
            ]
        }
        cls = build_entity_types(ontology)['HyperScaler']
        assert cls.__doc__ == 'Cloud capex cycle'

    def test_reserved_attribute_renamed(self):
        ontology = {
            'entity_types': [
                {
                    'name': 'Event',
                    'description': '...',
                    'attributes': [
                        {'name': 'name', 'type': 'text', 'description': 'X'},
                        {'name': 'summary', 'type': 'text', 'description': 'Y'},
                    ],
                }
            ]
        }
        cls = build_entity_types(ontology)['Event']
        # 예약 이름은 entity_ prefix
        instance = cls(entity_name='foo', entity_summary='bar')
        assert instance.entity_name == 'foo'
        assert instance.entity_summary == 'bar'

    def test_empty_ontology_returns_empty_dict(self):
        assert build_entity_types({}) == {}
        assert build_entity_types({'entity_types': []}) == {}

    def test_missing_description_has_default(self):
        ontology = {'entity_types': [{'name': 'Foo'}]}
        cls = build_entity_types(ontology)['Foo']
        assert 'A Foo entity' in (cls.__doc__ or '')

    def test_missing_attributes_list_ok(self):
        ontology = {'entity_types': [{'name': 'Foo', 'description': '...'}]}
        cls = build_entity_types(ontology)['Foo']
        # 속성 없이 초기화 가능
        instance = cls()
        assert isinstance(instance, BaseModel)


class TestBuildEdgeTypes:
    def test_edge_classes_created(self):
        ontology = {
            'edge_types': [
                {'name': 'INVESTS_IN', 'description': 'Capex'},
                {'name': 'SUPPLIES_TO', 'description': 'BOM flow'},
            ]
        }
        edges = build_edge_types(ontology)
        assert set(edges.keys()) == {'INVESTS_IN', 'SUPPLIES_TO'}
        assert issubclass(edges['INVESTS_IN'], BaseModel)

    def test_edge_attributes(self):
        ontology = {
            'edge_types': [
                {
                    'name': 'INVESTS_IN',
                    'description': 'Capex',
                    'attributes': [
                        {'name': 'deal_size', 'type': 'text',
                         'description': 'USD amount'}
                    ],
                }
            ]
        }
        cls = build_edge_types(ontology)['INVESTS_IN']
        instance = cls(deal_size='$1B')
        assert instance.deal_size == '$1B'

    def test_edge_without_attributes(self):
        ontology = {
            'edge_types': [
                {'name': 'COMPETES_WITH', 'description': 'Rival'}
            ]
        }
        cls = build_edge_types(ontology)['COMPETES_WITH']
        # no attributes → still valid BaseModel
        instance = cls()
        assert isinstance(instance, BaseModel)


class TestNoZepImport:
    def test_module_has_no_zep_cloud_dep(self):
        import app.services.graph_builder as module
        src = module.__file__
        with open(src, encoding='utf-8') as f:
            text = f.read()
        assert 'zep_cloud' not in text
        assert 'from zep' not in text


# ═══════════════════════════════════════════════════════════════════════
# TestGetGraphData — 오프라인(mocked driver) + 셰이프 변환 검증
# ═══════════════════════════════════════════════════════════════════════
import uuid as _uuid  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import patch  # noqa: E402

from app.services.graph_builder import GraphBuilderService  # noqa: E402


def _mock_graphiti_config():
    return SimpleNamespace(
        neo4j_uri='bolt://localhost:7687',
        neo4j_user='neo4j',
        neo4j_password='x',
        neo4j_database='neo4j',
        openai_api_key='sk-test',
    )


class TestGetGraphData:
    """get_graph_data: fetch_all_nodes/edges 결과를 view payload로 변환."""

    def test_shape_nodes_strip_entity_label_and_structure(self):
        raw_nodes = [
            {
                'uuid': 'n1', 'name': 'OpenAI',
                'labels': ['Entity', 'Company'],
                'summary': 'AI lab',
                'attributes': {'ticker': None},
                'created_at': '2026-04-19T10:00:00',
            },
            {
                'uuid': 'n2', 'name': 'Nvidia',
                'labels': ['Entity', 'HyperScaler', 'Company'],
                'summary': None,
                'attributes': {},
                'created_at': '2026-04-19T10:01:00',
            },
        ]
        raw_edges = [
            {
                'uuid': 'e1', 'name': 'COMPETES_WITH', 'fact': 'rivals',
                'source_node_uuid': 'n1', 'target_node_uuid': 'n2',
                'created_at': '2026-04-19T10:02:00',
            }
        ]

        svc = GraphBuilderService(graphiti_config=_mock_graphiti_config())
        with patch('app.services.graph_builder.neo4j_driver') as mock_driver, \
             patch('app.services.graph_builder.fetch_all_nodes', return_value=raw_nodes), \
             patch('app.services.graph_builder.fetch_all_edges', return_value=raw_edges):
            mock_driver.return_value = SimpleNamespace(close=lambda: None)
            result = svc.get_graph_data('group_xyz')

        assert result['graph_id'] == 'group_xyz'
        assert result['node_count'] == 2
        assert result['edge_count'] == 1

        n1 = next(n for n in result['nodes'] if n['uuid'] == 'n1')
        assert n1['name'] == 'OpenAI'
        # Entity 라벨은 제거되고 구체 라벨만 남음
        assert 'Entity' not in n1['labels']
        assert 'Company' in n1['labels']

        n2 = next(n for n in result['nodes'] if n['uuid'] == 'n2')
        assert set(n2['labels']) == {'HyperScaler', 'Company'}

        e1 = result['edges'][0]
        assert e1['source_node_uuid'] == 'n1'
        assert e1['target_node_uuid'] == 'n2'
        assert e1['fact'] == 'rivals'

    def test_empty_graph_returns_empty_lists(self):
        svc = GraphBuilderService(graphiti_config=_mock_graphiti_config())
        with patch('app.services.graph_builder.neo4j_driver') as mock_driver, \
             patch('app.services.graph_builder.fetch_all_nodes', return_value=[]), \
             patch('app.services.graph_builder.fetch_all_edges', return_value=[]):
            mock_driver.return_value = SimpleNamespace(close=lambda: None)
            result = svc.get_graph_data('missing_group')

        assert result['nodes'] == []
        assert result['edges'] == []
        assert result['node_count'] == 0
        assert result['edge_count'] == 0

    def test_driver_closed_even_on_fetch_exception(self):
        """fetch 중 예외 나도 driver.close()는 finally에서 호출돼야 함."""
        svc = GraphBuilderService(graphiti_config=_mock_graphiti_config())
        closed = []
        fake_driver = SimpleNamespace(close=lambda: closed.append(True))

        with patch('app.services.graph_builder.neo4j_driver', return_value=fake_driver), \
             patch('app.services.graph_builder.fetch_all_nodes',
                   side_effect=RuntimeError('neo4j unavailable')):
            try:
                svc.get_graph_data('g1')
            except RuntimeError:
                pass

        assert closed == [True], 'driver.close()는 finally에서 반드시 호출돼야 함'

    def test_attributes_dict_default_empty(self):
        """attributes가 None이어도 빈 dict로 반환."""
        raw_nodes = [{
            'uuid': 'n1', 'name': 'X', 'labels': ['Entity'],
            'summary': None, 'attributes': None, 'created_at': None,
        }]
        svc = GraphBuilderService(graphiti_config=_mock_graphiti_config())
        with patch('app.services.graph_builder.neo4j_driver') as mock_driver, \
             patch('app.services.graph_builder.fetch_all_nodes', return_value=raw_nodes), \
             patch('app.services.graph_builder.fetch_all_edges', return_value=[]):
            mock_driver.return_value = SimpleNamespace(close=lambda: None)
            result = svc.get_graph_data('g1')
        assert result['nodes'][0]['attributes'] == {}


# ═══════════════════════════════════════════════════════════════════════
# Tier B — live Neo4j (MIROFISH_NEO4J=1 게이트)
# ═══════════════════════════════════════════════════════════════════════
import pytest  # noqa: E402

NEO4J_ENABLED = os.environ.get('MIROFISH_NEO4J') == '1'


def _ensure_neo4j():
    if not NEO4J_ENABLED:
        pytest.skip(
            'Neo4j live 테스트는 기본 비활성화. MIROFISH_NEO4J=1 + docker 기동 후 실행.'
        )


class TestGraphBuilderLive:
    """live Neo4j: seed → get_graph_data → delete_graph → empty 검증."""

    def test_get_and_delete_lifecycle(self):
        _ensure_neo4j()
        from app.utils.graphiti_client import GraphitiConfig, neo4j_driver as real_driver

        config = GraphitiConfig.from_env()
        gid = f'phase6_builder_smoke_{_uuid.uuid4().hex[:8]}'

        # seed: 노드 2개 + 엣지 1개 직접 Cypher로 주입 (graphiti.add_episode 생략 —
        # 이 테스트는 순수 get_graph_data/delete_graph API만 검증)
        driver = real_driver(config)
        try:
            with driver.session(database=config.neo4j_database) as session:
                session.run(
                    """
                    CREATE (a:Entity {uuid: 'a', name: 'A', group_id: $gid,
                        created_at: '2026-04-19', summary: 's-a'})
                    CREATE (b:Entity {uuid: 'b', name: 'B', group_id: $gid,
                        created_at: '2026-04-19', summary: 's-b'})
                    CREATE (a)-[:RELATES_TO {uuid: 'e1', name: 'REL',
                        fact: 'a-b', group_id: $gid,
                        created_at: '2026-04-19'}]->(b)
                    """,
                    gid=gid,
                )
        finally:
            driver.close()

        svc = GraphBuilderService(graphiti_config=config)

        # get_graph_data
        data = svc.get_graph_data(gid)
        assert data['node_count'] == 2
        assert data['edge_count'] == 1
        assert {n['name'] for n in data['nodes']} == {'A', 'B'}
        assert data['edges'][0]['fact'] == 'a-b'

        # delete_graph
        svc.delete_graph(gid)

        # 삭제 후 empty 확인
        data_after = svc.get_graph_data(gid)
        assert data_after['node_count'] == 0
        assert data_after['edge_count'] == 0

    def test_delete_graph_non_existent_group_is_idempotent(self):
        _ensure_neo4j()
        from app.utils.graphiti_client import GraphitiConfig

        svc = GraphBuilderService(graphiti_config=GraphitiConfig.from_env())
        # 존재하지 않는 group_id 삭제는 no-op (예외 없음)
        svc.delete_graph(f'nonexistent_{_uuid.uuid4().hex[:8]}')
