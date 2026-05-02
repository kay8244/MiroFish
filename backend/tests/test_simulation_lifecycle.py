"""
시뮬레이션 라이프사이클 라우트 integration tests (`app/api/simulation/lifecycle.py`).

라우트 6개:
- POST /start                    : SimulationManager + SimulationRunner.start_simulation
- POST /stop                     : SimulationRunner.stop_simulation
- GET  /<sim>/run-status         : SimulationRunner.get_run_state
- GET  /<sim>/run-status/detail  : + get_all_actions
- POST /env-status               : SimulationRunner.check_env_alive + get_env_status_detail
- POST /close-env                : SimulationRunner.close_simulation_env
"""

import pytest

from app.api.simulation import lifecycle as lifecycle_routes
from app.services.simulation_manager import SimulationStatus
from app.services.simulation_runner import SimulationLimitError


# ---------------------------------------------------------------------------
# 가짜 객체
# ---------------------------------------------------------------------------

class _FakeRunState:
    def __init__(self, status="running", current_round=0, rounds=None, **extra):
        self.runner_status = type("S", (), {"value": status})()
        self.current_round = current_round
        self.rounds = rounds or []
        self._extra = {
            "runner_status": status,
            "current_round": current_round,
            **extra,
        }

    def to_dict(self):
        return self._extra


class _FakeAction:
    def __init__(self, **kw):
        self._d = kw

    def to_dict(self):
        return self._d


class _FakeState:
    def __init__(self, status=SimulationStatus.READY, project_id="p1", graph_id="g1"):
        self.status = status
        self.project_id = project_id
        self.graph_id = graph_id


@pytest.fixture
def fake_manager(monkeypatch):
    """SimulationManager 클래스를 치환해 메모리 상 sim state 다룸."""
    state_holder = {"sim_x": _FakeState()}
    saved = []

    class _M:
        def get_simulation(self, sim_id):
            return state_holder.get(sim_id)

        def _save_simulation_state(self, state):
            saved.append((state.status, state.project_id))

    monkeypatch.setattr(lifecycle_routes, "SimulationManager", _M)
    return {"states": state_holder, "saved": saved}


@pytest.fixture
def fake_runner(monkeypatch):
    """SimulationRunner 정적 메서드 치환."""
    calls = []

    class _R:
        @staticmethod
        def start_simulation(**kw):
            calls.append(("start", kw))
            return _FakeRunState(status="running", simulation_id=kw["simulation_id"])

        @staticmethod
        def stop_simulation(simulation_id):
            calls.append(("stop", simulation_id))
            return _FakeRunState(status="stopped", simulation_id=simulation_id)

        @staticmethod
        def get_run_state(simulation_id):
            calls.append(("get_run_state", simulation_id))
            return _FakeRunState(
                status="running",
                current_round=3,
                rounds=[1, 2, 3],
                simulation_id=simulation_id,
            )

        @staticmethod
        def get_all_actions(simulation_id, platform=None, round_num=None):
            calls.append(("get_all_actions", simulation_id, platform, round_num))
            return [_FakeAction(platform=platform or "twitter", round=round_num or 1)]

        @staticmethod
        def check_env_alive(simulation_id):
            calls.append(("check_env_alive", simulation_id))
            return True

        @staticmethod
        def get_env_status_detail(simulation_id):
            calls.append(("env_detail", simulation_id))
            return {"twitter_available": True, "reddit_available": True}

        @staticmethod
        def close_simulation_env(simulation_id, timeout):
            calls.append(("close", simulation_id, timeout))
            return {"success": True, "message": "ok"}

        @staticmethod
        def cleanup_simulation_logs(simulation_id):
            calls.append(("cleanup", simulation_id))
            return {"success": True}

    monkeypatch.setattr(lifecycle_routes, "SimulationRunner", _R)
    return {"calls": calls, "cls": _R}


# ============================================================================
# 인증 게이트
# ============================================================================

class TestAuthGate:
    @pytest.mark.parametrize("method,path", [
        ("post", "/api/simulation/start"),
        ("post", "/api/simulation/stop"),
        ("get",  "/api/simulation/sim_x/run-status"),
        ("get",  "/api/simulation/sim_x/run-status/detail"),
        ("post", "/api/simulation/env-status"),
        ("post", "/api/simulation/close-env"),
    ])
    def test_requires_auth(self, client, method, path):
        fn = getattr(client, method)
        resp = fn(path, json={}) if method == "post" else fn(path)
        assert resp.status_code == 401


# ============================================================================
# POST /start
# ============================================================================

class TestStart:
    def test_missing_sim_id_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/start", json={})
        assert resp.status_code == 400
        assert "simulation_id" in resp.get_json()["error"]

    def test_invalid_max_rounds_negative(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/start",
            json={"simulation_id": "sim_x", "max_rounds": -5},
        )
        assert resp.status_code == 400
        assert "max_rounds" in resp.get_json()["error"]

    def test_invalid_max_rounds_non_int(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/start",
            json={"simulation_id": "sim_x", "max_rounds": "abc"},
        )
        assert resp.status_code == 400

    def test_invalid_platform(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/start",
            json={"simulation_id": "sim_x", "platform": "facebook"},
        )
        assert resp.status_code == 400
        assert "platform" in resp.get_json()["error"].lower() or "플랫폼" in resp.get_json()["error"]

    def test_unknown_simulation_404(
        self, client, builder_user, login_as, fake_manager, fake_runner
    ):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/start",
            json={"simulation_id": "unknown"},
        )
        assert resp.status_code == 404

    def test_happy_path_ready_state(
        self, client, builder_user, login_as, fake_manager, fake_runner
    ):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/start",
            json={"simulation_id": "sim_x", "platform": "parallel"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        # state 가 RUNNING 으로 저장됨
        assert any(s == SimulationStatus.RUNNING for s, _ in fake_manager["saved"])

    def test_graph_memory_requires_graph_id(
        self, client, builder_user, login_as, fake_manager, fake_runner
    ):
        # graph_id 를 None 으로 만든 sim
        fake_manager["states"]["sim_no_graph"] = _FakeState(graph_id=None)

        # ProjectManager.get_project 가 graph_id 없는 project 반환하도록 패치
        class _Project:
            graph_id = None

        import app.api.simulation.lifecycle as L
        L.ProjectManager.get_project = staticmethod(lambda _: _Project())

        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/start",
            json={
                "simulation_id": "sim_no_graph",
                "enable_graph_memory_update": True,
            },
        )
        assert resp.status_code == 400
        assert "graph_id" in resp.get_json()["error"]

    def test_simulation_limit_429(
        self, client, builder_user, login_as, fake_manager, monkeypatch
    ):
        class _R:
            @staticmethod
            def start_simulation(**kw):
                raise SimulationLimitError("too many")

            # 다른 메서드들은 호출되지 않지만 안전하게 stub
            @staticmethod
            def get_run_state(_):
                return None

        monkeypatch.setattr(lifecycle_routes, "SimulationRunner", _R)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/start",
            json={"simulation_id": "sim_x"},
        )
        assert resp.status_code == 429


# ============================================================================
# POST /stop
# ============================================================================

class TestStop:
    def test_missing_sim_id_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/stop", json={})
        assert resp.status_code == 400

    def test_happy_path(
        self, client, builder_user, login_as, fake_manager, fake_runner
    ):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/stop", json={"simulation_id": "sim_x"}
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["runner_status"] == "stopped"
        # PAUSED 로 저장
        assert any(s == SimulationStatus.PAUSED for s, _ in fake_manager["saved"])

    def test_value_error_400(
        self, client, builder_user, login_as, monkeypatch, fake_manager
    ):
        class _R:
            @staticmethod
            def stop_simulation(_):
                raise ValueError("not running")

        monkeypatch.setattr(lifecycle_routes, "SimulationRunner", _R)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/stop", json={"simulation_id": "sim_x"}
        )
        assert resp.status_code == 400


# ============================================================================
# GET /<sim>/run-status
# ============================================================================

class TestRunStatus:
    def test_idle_when_no_state(self, client, viewer_user, login_as, monkeypatch):
        class _R:
            @staticmethod
            def get_run_state(_):
                return None

        monkeypatch.setattr(lifecycle_routes, "SimulationRunner", _R)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/run-status")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["runner_status"] == "idle"
        assert data["total_actions_count"] == 0

    def test_returns_state(self, client, viewer_user, login_as, fake_runner):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/run-status")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["runner_status"] == "running"


# ============================================================================
# GET /<sim>/run-status/detail
# ============================================================================

class TestRunStatusDetail:
    def test_idle_returns_empty_actions(
        self, client, viewer_user, login_as, monkeypatch
    ):
        class _R:
            @staticmethod
            def get_run_state(_):
                return None

        monkeypatch.setattr(lifecycle_routes, "SimulationRunner", _R)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/run-status/detail")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["all_actions"] == []
        assert data["twitter_actions"] == []
        assert data["reddit_actions"] == []

    def test_running_returns_actions(self, client, viewer_user, login_as, fake_runner):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/run-status/detail")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        # all_actions / twitter_actions / reddit_actions 가 모두 채워짐
        assert "all_actions" in data
        assert "twitter_actions" in data
        assert "reddit_actions" in data
        assert data["rounds_count"] == 3

    def test_platform_filter(
        self, client, viewer_user, login_as, fake_runner
    ):
        login_as("viewer@test.local")
        resp = client.get(
            "/api/simulation/sim_x/run-status/detail?platform=twitter"
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        # 필터가 twitter 면 reddit_actions 는 빈 리스트
        assert data["reddit_actions"] == []


# ============================================================================
# POST /env-status
# ============================================================================

class TestEnvStatus:
    def test_missing_sim_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/env-status", json={})
        assert resp.status_code == 400

    def test_alive(self, client, builder_user, login_as, fake_runner):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/env-status", json={"simulation_id": "sim_x"}
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["env_alive"] is True
        assert data["twitter_available"] is True
        assert data["reddit_available"] is True

    def test_dead_message(self, client, builder_user, login_as, monkeypatch):
        class _R:
            @staticmethod
            def check_env_alive(_):
                return False
            @staticmethod
            def get_env_status_detail(_):
                return {"twitter_available": False, "reddit_available": False}

        monkeypatch.setattr(lifecycle_routes, "SimulationRunner", _R)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/env-status", json={"simulation_id": "sim_x"}
        )
        data = resp.get_json()["data"]
        assert data["env_alive"] is False
        assert "종료" in data["message"] or "실행 중이 아니" in data["message"]


# ============================================================================
# POST /close-env
# ============================================================================

class TestCloseEnv:
    def test_missing_sim_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/close-env", json={})
        assert resp.status_code == 400

    def test_happy_path(
        self, client, builder_user, login_as, fake_manager, fake_runner
    ):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/close-env",
            json={"simulation_id": "sim_x", "timeout": 10},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        # COMPLETED 로 저장
        assert any(s == SimulationStatus.COMPLETED for s, _ in fake_manager["saved"])
        # timeout 이 전달됨
        close_call = [c for c in fake_runner["calls"] if c[0] == "close"][-1]
        assert close_call == ("close", "sim_x", 10)

    def test_value_error_400(self, client, builder_user, login_as, monkeypatch):
        class _R:
            @staticmethod
            def close_simulation_env(**kw):
                raise ValueError("bad state")

        monkeypatch.setattr(lifecycle_routes, "SimulationRunner", _R)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/close-env", json={"simulation_id": "sim_x"}
        )
        assert resp.status_code == 400
