"""
Phase 1 유틸리티 테스트.

Neo4j 연결이 필요한 테스트는 기본 skip. 환경변수 `MIROFISH_NEO4J=1`로 enable.
graph_purge / graphiti_paging은 live Neo4j + 실제 Graphiti 인스턴스로 왕복 검증.
ontology_generator.generate_python_code는 live 의존성 없이 문자열 검증만.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.ontology_generator import OntologyGenerator  # noqa: E402


NEO4J_ENABLED = os.environ.get("MIROFISH_NEO4J") == "1"


def _require_neo4j():
    if not NEO4J_ENABLED:
        pytest.skip(
            "Neo4j live 테스트는 기본 비활성화. `MIROFISH_NEO4J=1` + docker neo4j "
            "기동 후 실행.",
            allow_module_level=False,
        )


# ═══ ontology_generator.generate_python_code (offline) ═══


class TestGeneratePythonCodeGraphiti:
    """Phase 1: zep_cloud 의존성 제거, Graphiti 호환 pydantic 코드 출력."""

    @pytest.fixture
    def gen(self):
        return OntologyGenerator.__new__(OntologyGenerator)

    @pytest.fixture
    def sample_ontology(self):
        return {
            "entity_types": [
                {
                    "name": "HyperScaler",
                    "description": "Cloud hyperscaler (Microsoft, Amazon, Google, Meta).",
                    "attributes": [
                        {"name": "company_name", "type": "text",
                         "description": "Official name"},
                        {"name": "ticker", "type": "text",
                         "description": "Stock ticker"},
                    ],
                },
                {
                    "name": "Person",
                    "description": "Fallback person.",
                    "attributes": [],
                },
            ],
            "edge_types": [
                {
                    "name": "INVESTS_IN",
                    "description": "Capex investment.",
                    "source_targets": [
                        {"source": "HyperScaler", "target": "FablessCompany"}
                    ],
                    "attributes": [
                        {"name": "deal_size", "type": "text",
                         "description": "Size"}
                    ],
                },
            ],
        }

    def test_no_zep_cloud_import(self, gen, sample_ontology):
        code = gen.generate_python_code(sample_ontology)
        assert "zep_cloud" not in code
        assert "EntityModel" not in code
        assert "EdgeModel" not in code
        assert "EntityText" not in code

    def test_pydantic_based(self, gen, sample_ontology):
        code = gen.generate_python_code(sample_ontology)
        assert "from pydantic import BaseModel, Field" in code
        assert "class HyperScaler(BaseModel):" in code
        assert "class Person(BaseModel):" in code
        # UPPER_SNAKE → PascalCase class name
        assert "class InvestsIn(BaseModel):" in code

    def test_attribute_optional_str(self, gen, sample_ontology):
        code = gen.generate_python_code(sample_ontology)
        assert "company_name: Optional[str] = Field(" in code
        assert "ticker: Optional[str] = Field(" in code
        assert "deal_size: Optional[str] = Field(" in code

    def test_empty_attributes_produces_pass(self, gen, sample_ontology):
        code = gen.generate_python_code(sample_ontology)
        # Person has no attributes → pass body
        lines = code.splitlines()
        # find Person class block
        person_idx = next(i for i, line in enumerate(lines)
                          if line.startswith("class Person("))
        # doc + pass
        body = lines[person_idx + 1:person_idx + 3]
        assert any("pass" in line for line in body)

    def test_generated_code_is_syntactically_valid(self, gen, sample_ontology):
        code = gen.generate_python_code(sample_ontology)
        # ast.parse는 문법 오류 시 SyntaxError
        ast.parse(code)

    def test_entity_types_dict_exports(self, gen, sample_ontology):
        code = gen.generate_python_code(sample_ontology)
        assert 'ENTITY_TYPES = {' in code
        assert '"HyperScaler": HyperScaler,' in code
        assert '"Person": Person,' in code
        assert 'EDGE_TYPES = {' in code
        assert '"INVESTS_IN": InvestsIn,' in code


# ═══ graphiti_paging + graph_purge (live Neo4j) ═══


@pytest.fixture
def neo4j_driver_fixture():
    _require_neo4j()
    from app.utils.graphiti_client import neo4j_driver
    driver = neo4j_driver()
    yield driver
    driver.close()


@pytest.fixture
def seeded_graph(neo4j_driver_fixture):
    """테스트용 Entity/RELATES_TO 노드 수작업 생성 (LLM 호출 없음)."""
    gid = "test-graphiti-utils"
    with neo4j_driver_fixture.session(database="neo4j") as session:
        session.run("MATCH (n:Entity {group_id: $gid}) DETACH DELETE n", gid=gid)
        session.run(
            """
            CREATE (a:Entity {
                uuid: 'e-aa', name: 'Microsoft', group_id: $gid,
                summary: 'hyperscaler', created_at: datetime()
            })
            CREATE (b:Entity {
                uuid: 'e-bb', name: 'NVIDIA', group_id: $gid,
                summary: 'fabless', created_at: datetime()
            })
            CREATE (a)-[:RELATES_TO {
                uuid: 'r-ab', name: 'INVESTS_IN', fact: 'MS invests in NVIDIA',
                group_id: $gid, created_at: datetime()
            }]->(b)
            """,
            gid=gid,
        )
    yield gid
    with neo4j_driver_fixture.session(database="neo4j") as session:
        session.run("MATCH (n:Entity {group_id: $gid}) DETACH DELETE n", gid=gid)


class TestGraphitiPaging:

    def test_fetch_all_nodes(self, neo4j_driver_fixture, seeded_graph):
        from app.utils.graphiti_paging import fetch_all_nodes
        nodes = fetch_all_nodes(neo4j_driver_fixture, group_id=seeded_graph)
        assert len(nodes) == 2
        names = {n["name"] for n in nodes}
        assert names == {"Microsoft", "NVIDIA"}
        uuids = {n["uuid"] for n in nodes}
        assert uuids == {"e-aa", "e-bb"}

    def test_fetch_all_edges(self, neo4j_driver_fixture, seeded_graph):
        from app.utils.graphiti_paging import fetch_all_edges
        edges = fetch_all_edges(neo4j_driver_fixture, group_id=seeded_graph)
        assert len(edges) == 1
        e = edges[0]
        assert e["uuid"] == "r-ab"
        assert e["source_node_uuid"] == "e-aa"
        assert e["target_node_uuid"] == "e-bb"
        assert e["fact"] == "MS invests in NVIDIA"

    def test_get_node_by_uuid_found(self, neo4j_driver_fixture, seeded_graph):
        from app.utils.graphiti_paging import get_node_by_uuid
        node = get_node_by_uuid(neo4j_driver_fixture, "e-aa")
        assert node is not None
        assert node["name"] == "Microsoft"

    def test_get_node_by_uuid_missing(self, neo4j_driver_fixture, seeded_graph):
        from app.utils.graphiti_paging import get_node_by_uuid
        node = get_node_by_uuid(neo4j_driver_fixture, "no-such-uuid")
        assert node is None

    def test_get_entity_edges(self, neo4j_driver_fixture, seeded_graph):
        from app.utils.graphiti_paging import get_entity_edges
        edges = get_entity_edges(neo4j_driver_fixture, "e-aa")
        assert len(edges) == 1
        assert edges[0]["other_node_uuid"] == "e-bb"


class TestGraphPurge:

    def test_purge_removes_nodes_and_edges(
        self, neo4j_driver_fixture, seeded_graph
    ):
        from app.utils.graph_purge import purge_group
        from app.utils.graphiti_paging import fetch_all_nodes
        result = purge_group(neo4j_driver_fixture, group_id=seeded_graph)
        assert result["nodes_deleted"] == 2
        remaining = fetch_all_nodes(neo4j_driver_fixture, group_id=seeded_graph)
        assert remaining == []

    def test_purge_empty_group_idempotent(self, neo4j_driver_fixture):
        from app.utils.graph_purge import purge_group
        result = purge_group(neo4j_driver_fixture, group_id="does-not-exist")
        assert result["nodes_deleted"] == 0
