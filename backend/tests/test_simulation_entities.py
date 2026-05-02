"""
시뮬레이션 엔티티 라우트 integration tests (`app/api/simulation/entities.py`).

라우트 3개:
- GET /api/simulation/entities/<graph_id>
- GET /api/simulation/entities/<graph_id>/<entity_uuid>
- GET /api/simulation/entities/<graph_id>/by-type/<entity_type>

GraphitiEntityReader 는 module-level import 된 심볼을 monkeypatch 로 치환해 Neo4j
의존을 끊는다. 라우트가 직접 `GraphitiEntityReader()` 를 생성하므로, 클래스 자리에
가짜 팩토리를 꽂으면 인스턴스화 + 호출 모두 가짜로 흐른다.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from app.api.simulation import entities as entities_routes
from app.utils.cache import entity_cache


@dataclass
class _FakeEntityNode:
    uuid: str
    name: str
    labels: List[str]
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
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


@dataclass
class _FakeFiltered:
    entities: List[_FakeEntityNode]
    entity_types: set
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class _FakeReader:
    """라우트가 호출하는 GraphitiEntityReader 자리 holder. 호출 인자 캡처."""

    last_instance: Optional["_FakeReader"] = None

    def __init__(self, *args, **kwargs):
        self.calls: List[tuple] = []
        _FakeReader.last_instance = self

    # filter_defined_entities → FilteredEntities
    def filter_defined_entities(self, *, graph_id, defined_entity_types, enrich_with_edges):
        self.calls.append(("filter", graph_id, defined_entity_types, enrich_with_edges))
        return _FakeFiltered(
            entities=[
                _FakeEntityNode(uuid="u1", name="Alpha", labels=["Person"]),
                _FakeEntityNode(uuid="u2", name="Beta", labels=["Company"]),
            ],
            entity_types={"Person", "Company"},
            total_count=10,
            filtered_count=2,
        )

    # get_entity_with_context → EntityNode | None
    def get_entity_with_context(self, graph_id, entity_uuid):
        self.calls.append(("get_one", graph_id, entity_uuid))
        if entity_uuid == "missing-uuid":
            return None
        return _FakeEntityNode(
            uuid=entity_uuid,
            name="Detail",
            labels=["Person"],
            summary="hello",
            attributes={"k": "v"},
        )

    # get_entities_by_type → List[EntityNode]
    def get_entities_by_type(self, *, graph_id, entity_type, enrich_with_edges):
        self.calls.append(("by_type", graph_id, entity_type, enrich_with_edges))
        if entity_type == "Empty":
            return []
        return [
            _FakeEntityNode(uuid="u3", name="Gamma", labels=[entity_type]),
        ]


@pytest.fixture(autouse=True)
def _patch_reader_and_cache(monkeypatch):
    """모든 테스트에 자동 적용 — Reader 치환 + entity_cache 비움."""
    entity_cache.clear()
    monkeypatch.setattr(entities_routes, "GraphitiEntityReader", _FakeReader)
    yield
    entity_cache.clear()
    _FakeReader.last_instance = None


# ============================================================================
# 인증 게이트
# ============================================================================

class TestAuthGate:
    def test_list_requires_auth(self, client):
        resp = client.get("/api/simulation/entities/g1")
        assert resp.status_code == 401

    def test_detail_requires_auth(self, client):
        resp = client.get("/api/simulation/entities/g1/u1")
        assert resp.status_code == 401

    def test_by_type_requires_auth(self, client):
        resp = client.get("/api/simulation/entities/g1/by-type/Person")
        assert resp.status_code == 401


# ============================================================================
# GET /entities/<graph_id>
# ============================================================================

class TestGetGraphEntities:
    def test_viewer_can_read(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert data["total_count"] == 10
        assert data["filtered_count"] == 2
        assert {e["name"] for e in data["entities"]} == {"Alpha", "Beta"}

    def test_default_query_params(self, client, viewer_user, login_as):
        """entity_types 미지정 시 None, enrich 기본 True."""
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1")
        assert resp.status_code == 200
        call = _FakeReader.last_instance.calls[-1]
        assert call == ("filter", "g1", None, True)

    def test_entity_types_query_parsed(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1?entity_types=Person,%20Company%20,Place")
        assert resp.status_code == 200
        call = _FakeReader.last_instance.calls[-1]
        # 공백 trim, 빈 토큰 제거
        assert call[2] == ["Person", "Company", "Place"]

    def test_enrich_false(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1?enrich=false")
        assert resp.status_code == 200
        call = _FakeReader.last_instance.calls[-1]
        assert call[3] is False

    def test_blank_graph_id_400(self, client, viewer_user, login_as):
        """공백뿐인 graph_id 는 400. 라우트 매칭상 실제로 공백만 들어오기 어렵지만
        빈 토큰 검증 코드 자체는 보호한다."""
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/%20%20%20")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert "graph_id" in body["error"]

    def test_cache_hit_avoids_second_reader_call(self, client, viewer_user, login_as):
        """동일 키 두 번째 요청은 reader 인스턴스를 새로 만들지 않아야 한다."""
        login_as("viewer@test.local")
        resp1 = client.get("/api/simulation/entities/g1")
        assert resp1.status_code == 200
        first_inst = _FakeReader.last_instance

        resp2 = client.get("/api/simulation/entities/g1")
        assert resp2.status_code == 200
        # 두 번째는 캐시 hit 이므로 새 인스턴스가 만들어지지 않음
        assert _FakeReader.last_instance is first_inst
        # 응답 body 동일
        assert resp1.get_json() == resp2.get_json()

    def test_cache_key_differs_by_query(self, client, viewer_user, login_as):
        """enrich 값이 다르면 캐시 키가 달라져 새 인스턴스 생성."""
        login_as("viewer@test.local")
        client.get("/api/simulation/entities/g1?enrich=true")
        first_inst = _FakeReader.last_instance
        client.get("/api/simulation/entities/g1?enrich=false")
        assert _FakeReader.last_instance is not first_inst

    def test_reader_exception_returns_500(
        self, client, viewer_user, login_as, monkeypatch
    ):
        class _Boom(_FakeReader):
            def filter_defined_entities(self, **kw):
                raise RuntimeError("neo4j down")

        monkeypatch.setattr(entities_routes, "GraphitiEntityReader", _Boom)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1")
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["success"] is False
        assert "neo4j down" in body["error"]


# ============================================================================
# GET /entities/<graph_id>/<entity_uuid>
# ============================================================================

class TestGetEntityDetail:
    def test_returns_entity(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1/u1")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["uuid"] == "u1"
        assert body["data"]["name"] == "Detail"

    def test_missing_entity_404(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1/missing-uuid")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["success"] is False
        assert "missing-uuid" in body["error"]

    def test_reader_exception_returns_500(
        self, client, viewer_user, login_as, monkeypatch
    ):
        class _Boom(_FakeReader):
            def get_entity_with_context(self, graph_id, entity_uuid):
                raise RuntimeError("kaput")

        monkeypatch.setattr(entities_routes, "GraphitiEntityReader", _Boom)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1/u1")
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False


# ============================================================================
# GET /entities/<graph_id>/by-type/<entity_type>
# ============================================================================

class TestGetEntitiesByType:
    def test_returns_list(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1/by-type/Person")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert data["entity_type"] == "Person"
        assert data["count"] == 1
        assert data["entities"][0]["name"] == "Gamma"

    def test_empty_list(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1/by-type/Empty")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["count"] == 0
        assert data["entities"] == []

    def test_enrich_default_true(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        client.get("/api/simulation/entities/g1/by-type/Person")
        call = _FakeReader.last_instance.calls[-1]
        assert call == ("by_type", "g1", "Person", True)

    def test_enrich_false(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        client.get("/api/simulation/entities/g1/by-type/Person?enrich=false")
        call = _FakeReader.last_instance.calls[-1]
        assert call[3] is False

    def test_reader_exception_returns_500(
        self, client, viewer_user, login_as, monkeypatch
    ):
        class _Boom(_FakeReader):
            def get_entities_by_type(self, **kw):
                raise RuntimeError("oops")

        monkeypatch.setattr(entities_routes, "GraphitiEntityReader", _Boom)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/entities/g1/by-type/Person")
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False
