"""
시뮬레이션 활동 피드 라우트 integration tests (`app/api/simulation/activity.py`).

라우트 5개 (모두 GET):
- /<sim>/actions      : SimulationRunner.get_actions
- /<sim>/timeline     : SimulationRunner.get_timeline
- /<sim>/agent-stats  : SimulationRunner.get_agent_stats
- /<sim>/posts        : sqlite3 직접 (uploads/simulations/<sim>/<platform>_simulation.db)
- /<sim>/comments     : sqlite3 직접 (reddit_simulation.db)
"""

import os
import sqlite3
from pathlib import Path

import pytest

from app.api.simulation import activity as activity_routes


# ---------------------------------------------------------------------------
# 가짜 액션 객체 (to_dict 만 갖춘 더미)
# ---------------------------------------------------------------------------

class _FakeAction:
    def __init__(self, **kw):
        self._d = kw

    def to_dict(self):
        return self._d


@pytest.fixture
def fake_runner(monkeypatch):
    """SimulationRunner 의 정적 메서드 3개를 모킹."""
    state = {"actions_calls": [], "timeline_calls": [], "stats_calls": []}

    def get_actions(simulation_id, limit, offset, platform, agent_id, round_num):
        state["actions_calls"].append(
            (simulation_id, limit, offset, platform, agent_id, round_num)
        )
        return [
            _FakeAction(id=1, agent_id=agent_id or 0, round=round_num or 0),
            _FakeAction(id=2, agent_id=agent_id or 0, round=round_num or 0),
        ]

    def get_timeline(simulation_id, start_round, end_round):
        state["timeline_calls"].append((simulation_id, start_round, end_round))
        return [{"round": 1}, {"round": 2}, {"round": 3}]

    def get_agent_stats(simulation_id):
        state["stats_calls"].append(simulation_id)
        return [{"agent_id": 0, "actions": 10}, {"agent_id": 1, "actions": 5}]

    monkeypatch.setattr(activity_routes.SimulationRunner, "get_actions", staticmethod(get_actions))
    monkeypatch.setattr(activity_routes.SimulationRunner, "get_timeline", staticmethod(get_timeline))
    monkeypatch.setattr(activity_routes.SimulationRunner, "get_agent_stats", staticmethod(get_agent_stats))
    return state


@pytest.fixture
def fake_uploads(tmp_path, monkeypatch):
    """BACKEND_DIR 을 tmp_path 로 치환해 uploads/simulations 가짜 위치 마련."""
    backend = tmp_path / "fake_backend"
    backend.mkdir()
    monkeypatch.setattr(activity_routes, "BACKEND_DIR", str(backend))
    return backend


def _create_post_db(sim_dir: Path, platform: str, rows):
    sim_dir.mkdir(parents=True, exist_ok=True)
    db = sim_dir / f"{platform}_simulation.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE post (id INTEGER PRIMARY KEY, content TEXT, created_at TEXT)"
    )
    conn.executemany("INSERT INTO post VALUES (?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


def _create_comment_db(sim_dir: Path, rows):
    sim_dir.mkdir(parents=True, exist_ok=True)
    db = sim_dir / "reddit_simulation.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE comment (id INTEGER PRIMARY KEY, post_id TEXT, content TEXT, created_at TEXT)"
    )
    conn.executemany("INSERT INTO comment VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


# ============================================================================
# 인증 게이트
# ============================================================================

class TestAuthGate:
    @pytest.mark.parametrize("path", [
        "/api/simulation/sim_x/actions",
        "/api/simulation/sim_x/timeline",
        "/api/simulation/sim_x/agent-stats",
        "/api/simulation/sim_x/posts",
        "/api/simulation/sim_x/comments",
    ])
    def test_requires_auth(self, client, path):
        assert client.get(path).status_code == 401


# ============================================================================
# /<sim>/actions
# ============================================================================

class TestActions:
    def test_default_pagination(self, client, viewer_user, login_as, fake_runner):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_a/actions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["count"] == 2
        # _validate_pagination(default 100, max 100) → (100, 0)
        sim_id, limit, offset, platform, agent_id, round_num = fake_runner["actions_calls"][-1]
        assert (limit, offset, platform, agent_id, round_num) == (100, 0, None, None, None)
        assert sim_id == "sim_a"

    def test_query_filters(self, client, viewer_user, login_as, fake_runner):
        login_as("viewer@test.local")
        resp = client.get(
            "/api/simulation/sim_a/actions"
            "?limit=20&offset=5&platform=twitter&agent_id=7&round_num=3"
        )
        assert resp.status_code == 200
        sim_id, limit, offset, platform, agent_id, round_num = fake_runner["actions_calls"][-1]
        assert (limit, offset, platform, agent_id, round_num) == (20, 5, "twitter", 7, 3)

    def test_limit_clamped(self, client, viewer_user, login_as, fake_runner):
        login_as("viewer@test.local")
        client.get("/api/simulation/sim_a/actions?limit=9999")
        _, limit, *_ = fake_runner["actions_calls"][-1]
        assert limit == 100  # max_limit clamp

    def test_invalid_limit_falls_back_to_default(
        self, client, viewer_user, login_as, fake_runner
    ):
        login_as("viewer@test.local")
        client.get("/api/simulation/sim_a/actions?limit=abc")
        _, limit, *_ = fake_runner["actions_calls"][-1]
        assert limit == 100

    def test_runner_exception_500(self, client, viewer_user, login_as, monkeypatch):
        def boom(**kw):
            raise RuntimeError("oops")
        monkeypatch.setattr(activity_routes.SimulationRunner, "get_actions", staticmethod(boom))
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_a/actions")
        assert resp.status_code == 500


# ============================================================================
# /<sim>/timeline
# ============================================================================

class TestTimeline:
    def test_default(self, client, viewer_user, login_as, fake_runner):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_a/timeline")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["rounds_count"] == 3
        sim_id, start, end = fake_runner["timeline_calls"][-1]
        assert (sim_id, start, end) == ("sim_a", 0, None)

    def test_with_range(self, client, viewer_user, login_as, fake_runner):
        login_as("viewer@test.local")
        client.get("/api/simulation/sim_a/timeline?start_round=2&end_round=5")
        _, start, end = fake_runner["timeline_calls"][-1]
        assert (start, end) == (2, 5)


# ============================================================================
# /<sim>/agent-stats
# ============================================================================

class TestAgentStats:
    def test_returns_stats(self, client, viewer_user, login_as, fake_runner):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_a/agent-stats")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["agents_count"] == 2
        assert fake_runner["stats_calls"][-1] == "sim_a"


# ============================================================================
# /<sim>/posts
# ============================================================================

class TestPosts:
    def test_missing_db_returns_empty(self, client, viewer_user, login_as, fake_uploads):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_no_db/posts")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert data["count"] == 0
        assert data["posts"] == []
        assert "데이터베이스가 존재하지 않습니다" in data["message"]
        assert data["platform"] == "reddit"  # default

    def test_returns_posts_from_db(self, client, viewer_user, login_as, fake_uploads):
        sim_dir = fake_uploads / "uploads" / "simulations" / "sim_p"
        _create_post_db(sim_dir, "reddit", [
            (1, "first", "2026-04-30T00:00:01"),
            (2, "second", "2026-04-30T00:00:02"),
        ])
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_p/posts")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert data["total"] == 2
        assert data["count"] == 2
        # ORDER BY created_at DESC
        assert [p["content"] for p in data["posts"]] == ["second", "first"]

    def test_platform_query_switches_db(
        self, client, viewer_user, login_as, fake_uploads
    ):
        sim_dir = fake_uploads / "uploads" / "simulations" / "sim_pp"
        _create_post_db(sim_dir, "twitter", [(1, "tw", "2026-04-30T00:00:00")])
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_pp/posts?platform=twitter")
        body = resp.get_json()
        assert body["data"]["platform"] == "twitter"
        assert body["data"]["count"] == 1

    def test_pagination_limit_offset(
        self, client, viewer_user, login_as, fake_uploads
    ):
        sim_dir = fake_uploads / "uploads" / "simulations" / "sim_pl"
        rows = [(i, f"c{i}", f"2026-04-30T00:00:{i:02d}") for i in range(1, 6)]
        _create_post_db(sim_dir, "reddit", rows)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_pl/posts?limit=2&offset=1")
        data = resp.get_json()["data"]
        assert data["total"] == 5
        assert data["count"] == 2

    def test_db_without_post_table_graceful(
        self, client, viewer_user, login_as, fake_uploads
    ):
        """post 테이블이 없는 DB 도 500 이 아니라 빈 리스트."""
        sim_dir = fake_uploads / "uploads" / "simulations" / "sim_empty"
        sim_dir.mkdir(parents=True)
        db = sim_dir / "reddit_simulation.db"
        sqlite3.connect(str(db)).close()  # 빈 DB
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_empty/posts")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["count"] == 0
        assert data["total"] == 0


# ============================================================================
# /<sim>/comments
# ============================================================================

class TestComments:
    def test_missing_db_returns_empty(self, client, viewer_user, login_as, fake_uploads):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/comments")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["count"] == 0
        assert data["comments"] == []

    def test_returns_all_comments(
        self, client, viewer_user, login_as, fake_uploads
    ):
        sim_dir = fake_uploads / "uploads" / "simulations" / "sim_c"
        _create_comment_db(sim_dir, [
            (1, "p1", "hi", "2026-04-30T00:00:01"),
            (2, "p2", "ho", "2026-04-30T00:00:02"),
        ])
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_c/comments")
        data = resp.get_json()["data"]
        assert data["count"] == 2

    def test_filter_by_post_id(
        self, client, viewer_user, login_as, fake_uploads
    ):
        sim_dir = fake_uploads / "uploads" / "simulations" / "sim_cf"
        _create_comment_db(sim_dir, [
            (1, "p1", "x", "2026-04-30T00:00:01"),
            (2, "p1", "y", "2026-04-30T00:00:02"),
            (3, "p2", "z", "2026-04-30T00:00:03"),
        ])
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_cf/comments?post_id=p1")
        data = resp.get_json()["data"]
        assert data["count"] == 2
        assert all(c["post_id"] == "p1" for c in data["comments"])

    def test_no_comment_table_graceful(
        self, client, viewer_user, login_as, fake_uploads
    ):
        sim_dir = fake_uploads / "uploads" / "simulations" / "sim_nc"
        sim_dir.mkdir(parents=True)
        db = sim_dir / "reddit_simulation.db"
        sqlite3.connect(str(db)).close()
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_nc/comments")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["count"] == 0
