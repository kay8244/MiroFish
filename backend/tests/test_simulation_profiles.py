"""
시뮬레이션 Profile 라우트 integration tests (`app/api/simulation/profiles.py`).

라우트 3개:
- GET  /<sim>/profiles            : SimulationManager.get_profiles
- GET  /<sim>/profiles/realtime   : 파일 직접 read + state.json (캐시 10초)
- POST /generate-profiles         : GraphitiEntityReader + OasisProfileGenerator
"""

import csv
import json
from pathlib import Path

import pytest

from app.api.simulation import profiles as profiles_routes
from app.config import Config
from app.utils.cache import entity_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    entity_cache.clear()
    yield
    entity_cache.clear()


@pytest.fixture
def sim_root(tmp_path, monkeypatch):
    root = tmp_path / "sims"
    root.mkdir()
    monkeypatch.setattr(Config, "OASIS_SIMULATION_DATA_DIR", str(root))
    return root


# ============================================================================
# 인증 게이트
# ============================================================================

class TestAuthGate:
    def test_profiles_requires_auth(self, client):
        assert client.get("/api/simulation/sim_x/profiles").status_code == 401

    def test_realtime_requires_auth(self, client):
        assert client.get("/api/simulation/sim_x/profiles/realtime").status_code == 401

    def test_generate_requires_auth(self, client):
        assert client.post("/api/simulation/generate-profiles", json={}).status_code == 401


# ============================================================================
# GET /<sim>/profiles
# ============================================================================

class TestGetProfiles:
    def test_returns_profiles(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        class _M:
            def get_profiles(self, sim_id, platform):
                captured["call"] = (sim_id, platform)
                return [{"name": "alice"}, {"name": "bob"}]

        monkeypatch.setattr(profiles_routes, "SimulationManager", _M)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_a/profiles")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["count"] == 2
        assert body["data"]["platform"] == "reddit"
        assert captured["call"] == ("sim_a", "reddit")

    def test_platform_query(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        class _M:
            def get_profiles(self, sim_id, platform):
                captured["platform"] = platform
                return []

        monkeypatch.setattr(profiles_routes, "SimulationManager", _M)
        login_as("viewer@test.local")
        client.get("/api/simulation/sim_a/profiles?platform=twitter")
        assert captured["platform"] == "twitter"

    def test_value_error_404(self, client, viewer_user, login_as, monkeypatch):
        class _M:
            def get_profiles(self, sim_id, platform):
                raise ValueError("no such sim")

        monkeypatch.setattr(profiles_routes, "SimulationManager", _M)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/profiles")
        assert resp.status_code == 404

    def test_other_exception_500(self, client, viewer_user, login_as, monkeypatch):
        class _M:
            def get_profiles(self, sim_id, platform):
                raise RuntimeError("kaboom")

        monkeypatch.setattr(profiles_routes, "SimulationManager", _M)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/profiles")
        assert resp.status_code == 500


# ============================================================================
# GET /<sim>/profiles/realtime
# ============================================================================

class TestRealtimeProfiles:
    def test_missing_sim_404(self, client, viewer_user, login_as, sim_root):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/no_sim/profiles/realtime")
        assert resp.status_code == 404

    def test_dir_no_files(self, client, viewer_user, login_as, sim_root):
        sim_id = "sim_e"
        (sim_root / sim_id).mkdir()
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/profiles/realtime")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["file_exists"] is False
        assert data["profiles"] == []

    def test_reddit_profiles_json(self, client, viewer_user, login_as, sim_root):
        sim_id = "sim_r"
        sim_dir = sim_root / sim_id
        sim_dir.mkdir()
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([{"name": "a"}, {"name": "b"}, {"name": "c"}]), encoding="utf-8"
        )
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/profiles/realtime")
        data = resp.get_json()["data"]
        assert data["file_exists"] is True
        assert data["count"] == 3
        assert data["platform"] == "reddit"

    def test_twitter_profiles_csv(self, client, viewer_user, login_as, sim_root):
        sim_id = "sim_tw"
        sim_dir = sim_root / sim_id
        sim_dir.mkdir()
        csv_path = sim_dir / "twitter_profiles.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["name", "bio"])
            w.writerow(["alice", "hi"])
            w.writerow(["bob", "yo"])
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/profiles/realtime?platform=twitter")
        data = resp.get_json()["data"]
        assert data["count"] == 2
        assert data["platform"] == "twitter"

    def test_state_marks_generating(self, client, viewer_user, login_as, sim_root):
        sim_id = "sim_g"
        sim_dir = sim_root / sim_id
        sim_dir.mkdir()
        (sim_dir / "state.json").write_text(
            json.dumps({"status": "preparing", "entities_count": 42}), encoding="utf-8"
        )
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/profiles/realtime")
        data = resp.get_json()["data"]
        assert data["is_generating"] is True
        assert data["total_expected"] == 42

    def test_caches_when_not_generating(
        self, client, viewer_user, login_as, sim_root
    ):
        """is_generating=False 일 때만 캐시 — 두 번째 호출은 cache hit."""
        sim_id = "sim_cache"
        sim_dir = sim_root / sim_id
        sim_dir.mkdir()
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([{"name": "a"}]), encoding="utf-8"
        )
        login_as("viewer@test.local")
        r1 = client.get(f"/api/simulation/{sim_id}/profiles/realtime")
        assert r1.status_code == 200
        # 직접 캐시 확인
        cached = entity_cache.get(f"profiles_realtime:{sim_id}:reddit")
        assert cached is not None

    def test_does_not_cache_when_generating(
        self, client, viewer_user, login_as, sim_root
    ):
        sim_id = "sim_no_cache"
        sim_dir = sim_root / sim_id
        sim_dir.mkdir()
        (sim_dir / "state.json").write_text(
            json.dumps({"status": "preparing"}), encoding="utf-8"
        )
        login_as("viewer@test.local")
        client.get(f"/api/simulation/{sim_id}/profiles/realtime")
        cached = entity_cache.get(f"profiles_realtime:{sim_id}:reddit")
        assert cached is None


# ============================================================================
# POST /generate-profiles
# ============================================================================

class TestGenerateProfiles:
    def test_missing_graph_id_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/generate-profiles", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert "graph_id" in body["error"]

    def test_no_entities_400(self, client, builder_user, login_as, monkeypatch):
        class _Reader:
            def filter_defined_entities(self, **kw):
                class _F:
                    filtered_count = 0
                    entities = []
                    entity_types = set()
                return _F()

        monkeypatch.setattr(profiles_routes, "GraphitiEntityReader", _Reader)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/generate-profiles", json={"graph_id": "g1"}
        )
        assert resp.status_code == 400
        assert "엔티티" in resp.get_json()["error"]

    def test_happy_path_reddit(self, client, builder_user, login_as, monkeypatch):
        class _Reader:
            def filter_defined_entities(self, **kw):
                class _F:
                    filtered_count = 2
                    entities = [object(), object()]
                    entity_types = {"Person"}
                return _F()

        class _Profile:
            def to_reddit_format(self):
                return {"format": "reddit"}
            def to_twitter_format(self):
                return {"format": "twitter"}
            def to_dict(self):
                return {"format": "raw"}

        class _Gen:
            def generate_profiles_from_entities(self, entities, use_llm):
                return [_Profile() for _ in entities]

        monkeypatch.setattr(profiles_routes, "GraphitiEntityReader", _Reader)
        monkeypatch.setattr(profiles_routes, "OasisProfileGenerator", _Gen)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/generate-profiles",
            json={"graph_id": "g1", "platform": "reddit"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["count"] == 2
        assert data["platform"] == "reddit"
        assert all(p == {"format": "reddit"} for p in data["profiles"])

    def test_happy_path_twitter(self, client, builder_user, login_as, monkeypatch):
        class _Reader:
            def filter_defined_entities(self, **kw):
                class _F:
                    filtered_count = 1
                    entities = [object()]
                    entity_types = {"Org"}
                return _F()

        class _Profile:
            def to_twitter_format(self):
                return {"format": "twitter"}

        class _Gen:
            def generate_profiles_from_entities(self, entities, use_llm):
                return [_Profile()]

        monkeypatch.setattr(profiles_routes, "GraphitiEntityReader", _Reader)
        monkeypatch.setattr(profiles_routes, "OasisProfileGenerator", _Gen)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/generate-profiles",
            json={"graph_id": "g1", "platform": "twitter"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["profiles"][0] == {"format": "twitter"}

    def test_viewer_forbidden_post(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.post(
            "/api/simulation/generate-profiles", json={"graph_id": "g1"}
        )
        assert resp.status_code == 403
