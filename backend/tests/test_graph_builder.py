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
