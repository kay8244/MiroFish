"""
Phase 3 — graphiti_entity_reader 테스트.

Tier A (오프라인): graphiti_paging 함수들을 monkeypatch로 가짜 페이로드 주입,
    매핑/필터/enrich 로직만 검증. 항상 실행.
Tier B (live Neo4j): MIROFISH_NEO4J=1일 때만. seeded graph로 end-to-end 검증.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


NEO4J_ENABLED = os.environ.get("MIROFISH_NEO4J") == "1"


def _require_neo4j():
    if not NEO4J_ENABLED:
        pytest.skip(
            "Neo4j live 테스트는 기본 비활성화. `MIROFISH_NEO4J=1` + docker neo4j "
            "기동 후 실행.",
            allow_module_level=False,
        )


# ═══════════════════════════════════════════════════════════════════════
# Tier A — 오프라인 (monkeypatch 기반)
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def fake_nodes():
    """graphiti_paging.fetch_all_nodes가 리턴할 법한 dict 리스트."""
    return [
        {
            "uuid": "n1",
            "name": "Microsoft",
            "group_id": "g1",
            "created_at": None,
            "summary": "Hyperscaler",
            "labels": ["Entity", "HyperScaler"],
            "attributes": {"uuid": "n1", "name": "Microsoft", "group_id": "g1",
                           "labels": ["Entity", "HyperScaler"], "ticker": "MSFT"},
        },
        {
            "uuid": "n2",
            "name": "NVIDIA",
            "group_id": "g1",
            "created_at": None,
            "summary": "Fabless GPU",
            "labels": ["Entity", "FablessCompany"],
            "attributes": {"uuid": "n2", "name": "NVIDIA", "group_id": "g1",
                           "labels": ["Entity", "FablessCompany"], "ticker": "NVDA"},
        },
        {
            # 기본 Entity 레이블만 — 사전 정의 엔티티에 해당 안 함
            "uuid": "n3",
            "name": "Jensen",
            "group_id": "g1",
            "created_at": None,
            "summary": None,
            "labels": ["Entity"],
            "attributes": {"uuid": "n3", "name": "Jensen",
                           "group_id": "g1", "labels": ["Entity"]},
        },
    ]


@pytest.fixture
def fake_edges():
    return [
        {
            "uuid": "e1",
            "name": "INVESTS_IN",
            "fact": "MS invests in NVIDIA",
            "source_node_uuid": "n1",
            "target_node_uuid": "n2",
            "group_id": "g1",
            "valid_at": None,
            "invalid_at": None,
            "created_at": None,
            "episodes": [],
        },
    ]


@pytest.fixture
def reader_cls(monkeypatch, fake_nodes, fake_edges):
    """GraphitiEntityReader를 monkeypatched paging으로 임포트."""
    import app.services.graphiti_entity_reader as mod

    monkeypatch.setattr(mod, "fetch_all_nodes",
                        lambda driver, group_id, **kw: list(fake_nodes))
    monkeypatch.setattr(mod, "fetch_all_edges",
                        lambda driver, group_id, **kw: list(fake_edges))

    def fake_get_node_by_uuid(driver, node_uuid=None, **kw):
        target = node_uuid
        for n in fake_nodes:
            if n["uuid"] == target:
                return n
        return None

    def fake_get_entity_edges(driver, node_uuid=None, **kw):
        target = node_uuid
        out = []
        for e in fake_edges:
            if e["source_node_uuid"] == target or e["target_node_uuid"] == target:
                other = (e["target_node_uuid"]
                         if e["source_node_uuid"] == target
                         else e["source_node_uuid"])
                out.append({**e, "other_node_uuid": other, "other_node_name": ""})
        return out

    monkeypatch.setattr(mod, "get_node_by_uuid", fake_get_node_by_uuid)
    monkeypatch.setattr(mod, "get_entity_edges", fake_get_entity_edges)

    # driver 주입: 테스트에선 쓰이지 않으므로 MagicMock
    reader = mod.GraphitiEntityReader(driver=MagicMock())
    return reader, mod


class TestGraphitiEntityReaderOffline:

    def test_get_all_nodes_maps_to_zep_shape(self, reader_cls):
        reader, _ = reader_cls
        nodes = reader.get_all_nodes("g1")
        assert len(nodes) == 3
        n1 = next(n for n in nodes if n["uuid"] == "n1")
        assert n1["name"] == "Microsoft"
        assert n1["labels"] == ["Entity", "HyperScaler"]
        assert n1["summary"] == "Hyperscaler"
        # attributes에서 메타 필드(uuid/name/group_id/labels) 는 제거돼야 함
        assert "uuid" not in n1["attributes"]
        assert "name" not in n1["attributes"]
        assert "group_id" not in n1["attributes"]
        assert "labels" not in n1["attributes"]
        # 도메인 속성만 남아야 함
        assert n1["attributes"].get("ticker") == "MSFT"

    def test_get_all_nodes_summary_null_defaults_empty(self, reader_cls):
        reader, _ = reader_cls
        nodes = reader.get_all_nodes("g1")
        n3 = next(n for n in nodes if n["uuid"] == "n3")
        assert n3["summary"] == ""

    def test_get_all_edges_maps_to_zep_shape(self, reader_cls):
        reader, _ = reader_cls
        edges = reader.get_all_edges("g1")
        assert len(edges) == 1
        e = edges[0]
        assert e["uuid"] == "e1"
        assert e["name"] == "INVESTS_IN"
        assert e["fact"] == "MS invests in NVIDIA"
        assert e["source_node_uuid"] == "n1"
        assert e["target_node_uuid"] == "n2"
        # attributes dict 존재
        assert isinstance(e["attributes"], dict)

    def test_filter_defined_entities_skips_entity_only(self, reader_cls):
        reader, _ = reader_cls
        result = reader.filter_defined_entities("g1", enrich_with_edges=False)
        # n3은 Entity 레이블만 있으므로 제외
        assert result.total_count == 3
        assert result.filtered_count == 2
        uuids = {e.uuid for e in result.entities}
        assert uuids == {"n1", "n2"}
        assert result.entity_types == {"HyperScaler", "FablessCompany"}

    def test_filter_defined_entities_type_filter(self, reader_cls):
        reader, _ = reader_cls
        result = reader.filter_defined_entities(
            "g1", defined_entity_types=["HyperScaler"], enrich_with_edges=False
        )
        assert result.filtered_count == 1
        assert result.entities[0].uuid == "n1"
        assert result.entity_types == {"HyperScaler"}

    def test_filter_defined_entities_enrich_with_edges(self, reader_cls):
        reader, _ = reader_cls
        result = reader.filter_defined_entities("g1", enrich_with_edges=True)
        n1 = next(e for e in result.entities if e.uuid == "n1")
        n2 = next(e for e in result.entities if e.uuid == "n2")

        # n1 → outgoing to n2
        assert len(n1.related_edges) == 1
        assert n1.related_edges[0]["direction"] == "outgoing"
        assert n1.related_edges[0]["target_node_uuid"] == "n2"
        assert len(n1.related_nodes) == 1
        assert n1.related_nodes[0]["uuid"] == "n2"

        # n2 → incoming from n1
        assert len(n2.related_edges) == 1
        assert n2.related_edges[0]["direction"] == "incoming"
        assert n2.related_edges[0]["source_node_uuid"] == "n1"

    def test_get_entities_by_type_delegates(self, reader_cls):
        reader, _ = reader_cls
        ents = reader.get_entities_by_type(
            "g1", entity_type="FablessCompany", enrich_with_edges=False
        )
        assert len(ents) == 1
        assert ents[0].uuid == "n2"

    def test_get_entity_with_context_found(self, reader_cls):
        reader, _ = reader_cls
        ent = reader.get_entity_with_context("g1", "n1")
        assert ent is not None
        assert ent.uuid == "n1"
        assert ent.name == "Microsoft"
        # 엣지/연관 노드 채워짐
        assert len(ent.related_edges) == 1
        assert ent.related_edges[0]["direction"] == "outgoing"
        assert len(ent.related_nodes) == 1
        assert ent.related_nodes[0]["uuid"] == "n2"

    def test_get_entity_with_context_missing_returns_none(self, reader_cls):
        reader, _ = reader_cls
        ent = reader.get_entity_with_context("g1", "does-not-exist")
        assert ent is None

    def test_get_node_edges_returns_zep_shape(self, reader_cls):
        reader, _ = reader_cls
        edges = reader.get_node_edges("n1")
        assert len(edges) == 1
        e = edges[0]
        assert e["uuid"] == "e1"
        assert e["source_node_uuid"] == "n1"
        assert e["target_node_uuid"] == "n2"
        assert e["fact"] == "MS invests in NVIDIA"


class TestDataclassCompat:
    """EntityNode/FilteredEntities 시그니처는 zep_entity_reader와 동일해야 함."""

    def test_entity_node_fields(self):
        from app.services.graphiti_entity_reader import EntityNode
        node = EntityNode(uuid="x", name="N", labels=["Entity", "X"],
                          summary="s", attributes={})
        assert node.uuid == "x"
        assert node.get_entity_type() == "X"
        d = node.to_dict()
        assert set(d.keys()) >= {"uuid", "name", "labels", "summary",
                                 "attributes", "related_edges", "related_nodes"}

    def test_filtered_entities_to_dict(self):
        from app.services.graphiti_entity_reader import (
            EntityNode, FilteredEntities
        )
        node = EntityNode(uuid="x", name="N", labels=["Entity", "X"],
                          summary="", attributes={})
        fe = FilteredEntities(entities=[node], entity_types={"X"},
                              total_count=1, filtered_count=1)
        d = fe.to_dict()
        assert d["entity_types"] == ["X"]
        assert d["filtered_count"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Tier B — live Neo4j (MIROFISH_NEO4J=1)
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def neo4j_driver_fixture():
    _require_neo4j()
    from app.utils.graphiti_client import neo4j_driver
    driver = neo4j_driver()
    yield driver
    driver.close()


@pytest.fixture
def seeded_graph_reader(neo4j_driver_fixture):
    gid = "test-graphiti-entity-reader"
    with neo4j_driver_fixture.session(database="neo4j") as session:
        session.run("MATCH (n:Entity {group_id: $gid}) DETACH DELETE n", gid=gid)
        session.run(
            """
            CREATE (a:Entity:HyperScaler {
                uuid: 'er-a', name: 'Microsoft', group_id: $gid,
                summary: 'hyperscaler', created_at: datetime(),
                ticker: 'MSFT'
            })
            CREATE (b:Entity:FablessCompany {
                uuid: 'er-b', name: 'NVIDIA', group_id: $gid,
                summary: 'gpu', created_at: datetime(),
                ticker: 'NVDA'
            })
            CREATE (c:Entity {
                uuid: 'er-c', name: 'Bystander', group_id: $gid,
                summary: '', created_at: datetime()
            })
            CREATE (a)-[:RELATES_TO {
                uuid: 'er-r1', name: 'INVESTS_IN', fact: 'MS invests in NVIDIA',
                group_id: $gid, created_at: datetime()
            }]->(b)
            """,
            gid=gid,
        )
    yield gid
    with neo4j_driver_fixture.session(database="neo4j") as session:
        session.run("MATCH (n:Entity {group_id: $gid}) DETACH DELETE n", gid=gid)


class TestGraphitiEntityReaderLive:

    def test_filter_defined_entities_live(
        self, neo4j_driver_fixture, seeded_graph_reader
    ):
        from app.services.graphiti_entity_reader import GraphitiEntityReader
        reader = GraphitiEntityReader(driver=neo4j_driver_fixture)
        result = reader.filter_defined_entities(seeded_graph_reader,
                                                enrich_with_edges=True)
        assert result.total_count == 3
        assert result.filtered_count == 2  # Bystander (Entity only) 제외
        assert "HyperScaler" in result.entity_types
        assert "FablessCompany" in result.entity_types

    def test_filter_with_type_filter_live(
        self, neo4j_driver_fixture, seeded_graph_reader
    ):
        from app.services.graphiti_entity_reader import GraphitiEntityReader
        reader = GraphitiEntityReader(driver=neo4j_driver_fixture)
        result = reader.filter_defined_entities(
            seeded_graph_reader, defined_entity_types=["HyperScaler"],
            enrich_with_edges=False,
        )
        assert result.filtered_count == 1
        assert result.entities[0].name == "Microsoft"

    def test_get_entity_with_context_live(
        self, neo4j_driver_fixture, seeded_graph_reader
    ):
        from app.services.graphiti_entity_reader import GraphitiEntityReader
        reader = GraphitiEntityReader(driver=neo4j_driver_fixture)
        ent = reader.get_entity_with_context(seeded_graph_reader, "er-a")
        assert ent is not None
        assert ent.name == "Microsoft"
        # Microsoft -> NVIDIA INVESTS_IN 엣지 하나
        assert len(ent.related_edges) == 1
        assert len(ent.related_nodes) == 1
        assert ent.related_nodes[0]["name"] == "NVIDIA"

    def test_get_node_edges_live(
        self, neo4j_driver_fixture, seeded_graph_reader
    ):
        from app.services.graphiti_entity_reader import GraphitiEntityReader
        reader = GraphitiEntityReader(driver=neo4j_driver_fixture)
        edges = reader.get_node_edges("er-a")
        assert len(edges) == 1
        assert edges[0]["fact"] == "MS invests in NVIDIA"
