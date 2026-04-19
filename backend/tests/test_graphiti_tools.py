"""
Phase 4 — graphiti_tools 테스트.

Tier A (오프라인): graphiti.search / graphiti_paging 함수들을 monkeypatch로
    가짜 페이로드 주입. SearchResult/NodeInfo/EdgeInfo 매핑 + 폴백 검증. 항상 실행.
Tier B (live Neo4j): MIROFISH_NEO4J=1일 때만. 실제 Neo4j seed graph로 quick_search,
    get_node_detail, get_all_nodes 검증.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
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
            "valid_at": "2024-01-01",
            "invalid_at": None,
            "created_at": None,
            "episodes": [],
        },
    ]


@pytest.fixture
def fake_entity_edges():
    """graphiti.search가 리턴하는 EntityEdge 흉내 객체."""
    return [
        SimpleNamespace(
            uuid="e1",
            name="INVESTS_IN",
            fact="MS invests in NVIDIA per recent filings",
            source_node_uuid="n1",
            target_node_uuid="n2",
        ),
        SimpleNamespace(
            uuid="e2",
            name="COMPETES_WITH",
            fact="NVIDIA competes with AMD on GPUs",
            source_node_uuid="n2",
            target_node_uuid="n3",
        ),
    ]


@pytest.fixture
def tools_factory(monkeypatch, fake_nodes, fake_edges):
    """driver/graphiti 주입 테스트 픽스처. 매번 새 인스턴스 반환."""
    import app.services.graphiti_tools as mod

    monkeypatch.setattr(mod, "fetch_all_nodes",
                        lambda driver, group_id, **kw: list(fake_nodes))
    monkeypatch.setattr(mod, "fetch_all_edges",
                        lambda driver, group_id, **kw: list(fake_edges))

    def fake_get_node_by_uuid(driver, node_uuid=None, **kw):
        for n in fake_nodes:
            if n["uuid"] == node_uuid:
                return n
        return None

    monkeypatch.setattr(mod, "get_node_by_uuid", fake_get_node_by_uuid)

    def _make(graphiti=None):
        driver = MagicMock(name="neo4j_driver")
        return mod.GraphitiToolsService(driver=driver, graphiti=graphiti)

    return _make


def test_init_lazy_graphiti(tools_factory):
    tools = tools_factory()
    assert tools._graphiti is None
    assert tools._driver is not None
    assert tools._owns_driver is False  # 주입했으므로 owns 아님


def test_get_all_nodes_maps_to_nodeinfo(tools_factory):
    tools = tools_factory()
    nodes = tools.get_all_nodes("g1")
    assert len(nodes) == 2
    msft = next(n for n in nodes if n.uuid == "n1")
    assert msft.name == "Microsoft"
    assert "HyperScaler" in msft.labels
    assert msft.summary == "Hyperscaler"
    # _META_ATTR_KEYS 제거 확인
    assert "uuid" not in msft.attributes
    assert "name" not in msft.attributes
    assert "labels" not in msft.attributes
    # 도메인 속성은 유지
    assert msft.attributes.get("ticker") == "MSFT"


def test_get_all_edges_maps_to_edgeinfo_with_temporal(tools_factory):
    tools = tools_factory()
    edges = tools.get_all_edges("g1", include_temporal=True)
    assert len(edges) == 1
    e = edges[0]
    assert e.uuid == "e1"
    assert e.name == "INVESTS_IN"
    assert e.fact == "MS invests in NVIDIA"
    assert e.source_node_uuid == "n1"
    assert e.target_node_uuid == "n2"
    assert e.valid_at == "2024-01-01"
    assert e.invalid_at is None


def test_get_node_detail_uses_paging_helper(tools_factory):
    tools = tools_factory()
    node = tools.get_node_detail("n2")
    assert node is not None
    assert node.name == "NVIDIA"
    assert "FablessCompany" in node.labels
    assert node.attributes.get("ticker") == "NVDA"
    # 메타 필드 제거
    assert "uuid" not in node.attributes


def test_get_node_detail_missing_returns_none(tools_factory):
    tools = tools_factory()
    assert tools.get_node_detail("nonexistent") is None


def test_search_graph_calls_graphiti_search(monkeypatch, tools_factory, fake_entity_edges):
    """graphiti.search → list[EntityEdge] → SearchResult 매핑."""
    import app.services.graphiti_tools as mod

    captured = {}

    async def fake_search(query, group_ids=None, num_results=10):
        captured["query"] = query
        captured["group_ids"] = group_ids
        captured["num_results"] = num_results
        return list(fake_entity_edges)

    fake_graphiti = SimpleNamespace(search=fake_search, close=lambda: _coro_none())

    async def _coro_none():
        return None

    tools = tools_factory(graphiti=fake_graphiti)
    result = tools.search_graph("g1", "AI investment", limit=5)

    assert captured["query"] == "AI investment"
    assert captured["group_ids"] == ["g1"]
    assert captured["num_results"] == 5

    assert result.total_count == 2
    assert result.facts == [
        "MS invests in NVIDIA per recent filings",
        "NVIDIA competes with AMD on GPUs",
    ]
    assert len(result.edges) == 2
    assert result.edges[0]["uuid"] == "e1"
    assert result.edges[0]["source_node_uuid"] == "n1"
    assert result.nodes == []  # graphiti.search는 edges만


def test_search_graph_nodes_scope_uses_local(tools_factory):
    """scope=='nodes'면 graphiti.search 우회하고 _local_search."""
    tools = tools_factory()  # graphiti=None — 호출되면 lazy init되므로 graphiti.search가 안 불려야 함
    result = tools.search_graph("g1", "Microsoft", limit=10, scope="nodes")
    # _local_search → fetch_all_nodes 픽스처 데이터 사용
    assert result.query == "Microsoft"
    # Microsoft가 매칭되어야 함
    assert any("Microsoft" in (n.get("name") or "") for n in result.nodes)


def test_search_graph_falls_back_to_local_on_error(monkeypatch, tools_factory):
    """graphiti.search가 raise → _local_search 폴백."""
    async def fake_search(*args, **kwargs):
        raise RuntimeError("graphiti boom")

    fake_graphiti = SimpleNamespace(search=fake_search)

    tools = tools_factory(graphiti=fake_graphiti)
    # _call_with_retry는 3번 재시도 후 raise → 그 다음 except에서 _local_search 호출
    # 재시도 delay를 0으로 줄여 테스트 속도 보장
    tools.MAX_RETRIES = 1
    tools.RETRY_DELAY = 0
    result = tools.search_graph("g1", "Microsoft", limit=5, scope="edges")
    # _local_search 결과 (edges scope에서 fact 매칭)
    assert result.query == "Microsoft"
    # MS invests in NVIDIA fact가 "Microsoft" 키워드 매칭은 안 되지만 (MS만 있음),
    # 적어도 폴백이 실행되어 SearchResult 객체가 정상 생성되어야 함
    assert result.total_count >= 0


def test_quick_search_delegates_to_search_graph(monkeypatch, tools_factory, fake_entity_edges):
    async def fake_search(query, group_ids=None, num_results=10):
        return list(fake_entity_edges)

    fake_graphiti = SimpleNamespace(search=fake_search)
    tools = tools_factory(graphiti=fake_graphiti)
    result = tools.quick_search("g1", "AI", limit=3)
    assert result.total_count == 2  # fake_entity_edges 길이


def test_get_entities_by_type(tools_factory):
    tools = tools_factory()
    msft_only = tools.get_entities_by_type("g1", "HyperScaler")
    assert len(msft_only) == 1
    assert msft_only[0].name == "Microsoft"

    nvda_only = tools.get_entities_by_type("g1", "FablessCompany")
    assert len(nvda_only) == 1
    assert nvda_only[0].name == "NVIDIA"

    none = tools.get_entities_by_type("g1", "NonExistentType")
    assert none == []


def test_get_graph_statistics(tools_factory):
    tools = tools_factory()
    stats = tools.get_graph_statistics("g1")
    assert stats["graph_id"] == "g1"
    assert stats["total_nodes"] == 2
    assert stats["total_edges"] == 1
    assert stats["entity_types"] == {"HyperScaler": 1, "FablessCompany": 1}
    assert stats["relation_types"] == {"INVESTS_IN": 1}


def test_get_node_edges_filters_by_uuid(tools_factory):
    tools = tools_factory()
    edges = tools.get_node_edges("g1", "n1")
    assert len(edges) == 1
    assert edges[0].source_node_uuid == "n1"

    edges_n2 = tools.get_node_edges("g1", "n2")
    assert len(edges_n2) == 1
    assert edges_n2[0].target_node_uuid == "n2"

    edges_orphan = tools.get_node_edges("g1", "nonexistent")
    assert edges_orphan == []


def test_zep_shim_aliases_to_graphiti(tools_factory):
    """zep_tools shim이 GraphitiToolsService로 redirect됐는지 확인."""
    from app.services.zep_tools import ZepToolsService
    from app.services.graphiti_tools import GraphitiToolsService
    assert ZepToolsService is GraphitiToolsService


# ═══════════════════════════════════════════════════════════════════════
# Tier B — live Neo4j (MIROFISH_NEO4J=1 게이트)
# ═══════════════════════════════════════════════════════════════════════


def _find_seeded_group_id(driver):
    """가장 노드가 많은 group_id 반환 (Phase 0~3에서 빌드된 그래프)."""
    with driver.session(database="neo4j") as session:
        rec = session.run(
            """
            MATCH (n:Entity)
            WHERE n.group_id IS NOT NULL
            RETURN n.group_id AS gid, count(n) AS cnt
            ORDER BY cnt DESC
            LIMIT 1
            """
        ).single()
        return rec["gid"] if rec else None


@pytest.fixture
def live_driver():
    _require_neo4j()
    from app.utils.graphiti_client import neo4j_driver
    drv = neo4j_driver()
    yield drv
    drv.close()


def test_live_get_all_nodes(live_driver):
    from app.services.graphiti_tools import GraphitiToolsService
    gid = _find_seeded_group_id(live_driver)
    if not gid:
        pytest.skip("seed된 group_id 없음 — 먼저 graph build 실행 필요")

    tools = GraphitiToolsService(driver=live_driver)
    nodes = tools.get_all_nodes(gid)
    assert len(nodes) > 0
    # 모든 노드가 NodeInfo 객체이고 uuid/name 존재
    for n in nodes[:5]:
        assert n.uuid
        assert isinstance(n.labels, list)


def test_live_get_node_detail(live_driver):
    from app.services.graphiti_tools import GraphitiToolsService
    gid = _find_seeded_group_id(live_driver)
    if not gid:
        pytest.skip("seed된 group_id 없음")

    tools = GraphitiToolsService(driver=live_driver)
    nodes = tools.get_all_nodes(gid)
    assert nodes, "노드 0개 — 시드 필요"

    target = nodes[0]
    fetched = tools.get_node_detail(target.uuid)
    assert fetched is not None
    assert fetched.uuid == target.uuid
    assert fetched.name == target.name


def test_live_quick_search(live_driver):
    """graphiti.search 라이브 호출 — 실제 OpenAI/Neo4j 통신."""
    from app.services.graphiti_tools import GraphitiToolsService
    gid = _find_seeded_group_id(live_driver)
    if not gid:
        pytest.skip("seed된 group_id 없음")

    tools = GraphitiToolsService(driver=live_driver)
    try:
        # 간단한 쿼리 — fact가 0건이어도 호출 자체가 raise하지 않으면 통과
        result = tools.quick_search(gid, "company", limit=3)
        assert result.query == "company"
        assert result.total_count >= 0  # 시드 데이터 의존하므로 0도 허용
        # facts가 있다면 모두 str
        for f in result.facts:
            assert isinstance(f, str)
    finally:
        tools.close()
