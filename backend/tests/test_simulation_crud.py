"""
시뮬레이션 CRUD 라우트 integration tests (`app/api/simulation/crud.py`).

라우트 6개:
- POST /create               : SimulationManager.create_simulation (+ ProjectManager 검증)
- POST /prepare              : 비동기 태스크 (TaskManager + 백그라운드 스레드)
- POST /prepare/status       : TaskManager.get_task / _check_simulation_prepared
- GET  /<sim>                : SimulationManager.get_simulation
- GET  /list                 : SimulationManager.list_simulations
- GET  /history              : list + 강화 (config + run_state + project + report)

prepare 의 백그라운드 스레드는 threading.Thread 를 monkeypatch 해 인라인 실행 차단.
"""

import pytest

from app.api.simulation import crud as crud_routes
from app.services.simulation_manager import SimulationStatus
from app.utils.rate_limiter import _limiter as _rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """rate_limit 데코레이터의 글로벌 버킷 초기화 — 테스트 간 격리."""
    _rate_limiter._buckets.clear()
    yield
    _rate_limiter._buckets.clear()


# ---------------------------------------------------------------------------
# 가짜 객체
# ---------------------------------------------------------------------------

class _FakeProject:
    def __init__(self, project_id="p1", graph_id="g1", simulation_requirement="요구사항"):
        self.project_id = project_id
        self.graph_id = graph_id
        self.simulation_requirement = simulation_requirement
        self.files = []


class _FakeSimState:
    def __init__(
        self,
        simulation_id="sim_1",
        project_id="p1",
        graph_id="g1",
        status=SimulationStatus.READY,
        simulation_requirement=None,
    ):
        self.simulation_id = simulation_id
        self.project_id = project_id
        self.graph_id = graph_id
        self.status = status
        self.simulation_requirement = simulation_requirement
        self.entities_count = 0
        self.entity_types = []
        self.created_at = "2026-04-30T00:00:00"
        self.updated_at = "2026-04-30T00:00:00"
        self.error = None

    def to_dict(self):
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "created_at": self.created_at,
            "entities_count": self.entities_count,
        }

    def to_simple_dict(self):
        return self.to_dict()


@pytest.fixture
def block_threads(monkeypatch):
    """threading.Thread 를 NO-OP 으로 — 백그라운드 작업 인라인 차단."""
    class _NoopThread:
        def __init__(self, **kw):
            pass
        def start(self):
            pass
    monkeypatch.setattr(crud_routes.threading, "Thread", _NoopThread)


# ============================================================================
# 인증 게이트
# ============================================================================

class TestAuthGate:
    @pytest.mark.parametrize("method,path", [
        ("post", "/api/simulation/create"),
        ("post", "/api/simulation/prepare"),
        ("post", "/api/simulation/prepare/status"),
        ("get",  "/api/simulation/sim_x"),
        ("get",  "/api/simulation/list"),
        ("get",  "/api/simulation/history"),
    ])
    def test_requires_auth(self, client, method, path):
        fn = getattr(client, method)
        resp = fn(path, json={}) if method == "post" else fn(path)
        assert resp.status_code == 401


# ============================================================================
# POST /create
# ============================================================================

class TestCreate:
    def test_missing_project_id(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/create", json={})
        assert resp.status_code == 400
        assert "project_id" in resp.get_json()["error"]

    def test_unknown_project_404(self, client, builder_user, login_as, monkeypatch):
        monkeypatch.setattr(crud_routes.ProjectManager, "get_project", staticmethod(lambda _: None))
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/create", json={"project_id": "ghost"}
        )
        assert resp.status_code == 404

    def test_no_graph_id_400(self, client, builder_user, login_as, monkeypatch):
        monkeypatch.setattr(
            crud_routes.ProjectManager, "get_project",
            staticmethod(lambda _: _FakeProject(graph_id=None)),
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/create", json={"project_id": "p1"}
        )
        assert resp.status_code == 400
        assert "그래프" in resp.get_json()["error"]

    def test_happy_path(self, client, builder_user, login_as, monkeypatch):
        monkeypatch.setattr(
            crud_routes.ProjectManager, "get_project",
            staticmethod(lambda _: _FakeProject()),
        )

        captured = {}

        class _M:
            def create_simulation(self, **kw):
                captured.update(kw)
                return _FakeSimState(project_id=kw["project_id"], graph_id=kw["graph_id"])

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/create",
            json={
                "project_id": "p1",
                "enable_twitter": False,
                "simulation_requirement": "  override  ",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert captured["project_id"] == "p1"
        assert captured["enable_twitter"] is False
        assert captured["enable_reddit"] is True  # default
        assert captured["simulation_requirement"] == "override"  # trimmed

    def test_viewer_forbidden(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.post(
            "/api/simulation/create", json={"project_id": "p1"}
        )
        assert resp.status_code == 403


# ============================================================================
# POST /prepare (백그라운드 스레드 차단 후 응답만 검증)
# ============================================================================

class TestPrepare:
    def test_missing_sim_id(self, client, builder_user, login_as, block_threads):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/prepare", json={})
        assert resp.status_code == 400

    def test_unknown_sim_404(self, client, builder_user, login_as, block_threads, monkeypatch):
        class _M:
            def get_simulation(self, _):
                return None

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/prepare", json={"simulation_id": "no"}
        )
        assert resp.status_code == 404

    def test_already_prepared_short_circuits(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState()

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            crud_routes,
            "_check_simulation_prepared",
            lambda _: (True, {"existing": True}),
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/prepare", json={"simulation_id": "sim_x"}
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["already_prepared"] is True
        assert body["data"]["status"] == "ready"

    def test_force_regenerate_starts_task(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        sim_state = _FakeSimState(simulation_requirement="X")

        class _M:
            def get_simulation(self, _):
                return sim_state
            def _save_simulation_state(self, s):
                pass

        # ProjectManager: 유효 프로젝트 + 텍스트
        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            crud_routes.ProjectManager, "get_project",
            staticmethod(lambda _: _FakeProject(simulation_requirement="X")),
        )
        monkeypatch.setattr(
            crud_routes.ProjectManager, "get_extracted_text",
            staticmethod(lambda _: "doc text"),
        )

        # GraphitiEntityReader 동기 카운트
        class _Reader:
            def filter_defined_entities(self, **kw):
                class _F:
                    filtered_count = 5
                    entity_types = {"Person"}
                return _F()

        monkeypatch.setattr(crud_routes, "GraphitiEntityReader", _Reader)

        # TaskManager
        class _TM:
            def create_task(self, **kw):
                return "task_123"
            def update_task(self, *a, **kw):
                pass
            def complete_task(self, *a, **kw):
                pass
            def fail_task(self, *a, **kw):
                pass

        monkeypatch.setattr(crud_routes, "TaskManager", _TM)

        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/prepare",
            json={"simulation_id": "sim_x", "force_regenerate": True},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["task_id"] == "task_123"
        assert body["data"]["status"] == "preparing"
        assert body["data"]["expected_entities_count"] == 5

    def test_no_simulation_requirement_400(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState(simulation_requirement=None)

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            crud_routes,
            "_check_simulation_prepared",
            lambda _: (False, {}),
        )
        # project 도 빈 requirement
        monkeypatch.setattr(
            crud_routes.ProjectManager, "get_project",
            staticmethod(lambda _: _FakeProject(simulation_requirement="")),
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/prepare", json={"simulation_id": "sim_x"}
        )
        assert resp.status_code == 400
        assert "요구사항" in resp.get_json()["error"]


# ============================================================================
# POST /prepare/status
# ============================================================================

class TestPrepareStatus:
    def test_no_ids_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/prepare/status", json={})
        assert resp.status_code == 400

    def test_simulation_id_already_prepared(
        self, client, builder_user, login_as, monkeypatch
    ):
        monkeypatch.setattr(
            crud_routes,
            "_check_simulation_prepared",
            lambda _: (True, {"info": "yes"}),
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/prepare/status",
            json={"simulation_id": "sim_x"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "ready"
        assert data["already_prepared"] is True

    def test_simulation_id_not_started(
        self, client, builder_user, login_as, monkeypatch
    ):
        monkeypatch.setattr(
            crud_routes,
            "_check_simulation_prepared",
            lambda _: (False, {}),
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/prepare/status",
            json={"simulation_id": "sim_x"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "not_started"
        assert data["already_prepared"] is False

    def test_unknown_task_id_404(self, client, builder_user, login_as, monkeypatch):
        class _TM:
            def get_task(self, _):
                return None

        monkeypatch.setattr(crud_routes, "TaskManager", _TM)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/prepare/status",
            json={"task_id": "task_ghost"},
        )
        assert resp.status_code == 404

    def test_returns_task_dict(self, client, builder_user, login_as, monkeypatch):
        class _Task:
            def to_dict(self):
                return {"task_id": "t1", "status": "processing", "progress": 50}

        class _TM:
            def get_task(self, _):
                return _Task()

        monkeypatch.setattr(crud_routes, "TaskManager", _TM)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/prepare/status",
            json={"task_id": "t1"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "processing"
        assert data["already_prepared"] is False


# ============================================================================
# GET /<sim>
# ============================================================================

class TestGetSim:
    def test_404(self, client, viewer_user, login_as, monkeypatch):
        class _M:
            def get_simulation(self, _):
                return None

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/no_sim")
        assert resp.status_code == 404

    def test_returns_state(self, client, viewer_user, login_as, monkeypatch):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState(status=SimulationStatus.PREPARING)

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["simulation_id"] == "sim_1"
        # READY 상태가 아니면 run_instructions 키 없음
        assert "run_instructions" not in data

    def test_ready_includes_run_instructions(
        self, client, viewer_user, login_as, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState(status=SimulationStatus.READY)
            def get_run_instructions(self, _):
                return {"how": "to run"}

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x")
        data = resp.get_json()["data"]
        assert data["run_instructions"] == {"how": "to run"}


# ============================================================================
# GET /list
# ============================================================================

class TestList:
    def test_returns_list(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        class _M:
            def list_simulations(self, project_id=None):
                captured["project_id"] = project_id
                return [_FakeSimState(simulation_id="s1"), _FakeSimState(simulation_id="s2")]

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/list")
        body = resp.get_json()
        assert resp.status_code == 200
        assert body["count"] == 2
        assert captured["project_id"] is None

    def test_filter_by_project(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        class _M:
            def list_simulations(self, project_id=None):
                captured["project_id"] = project_id
                return []

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        login_as("viewer@test.local")
        client.get("/api/simulation/list?project_id=p9")
        assert captured["project_id"] == "p9"


# ============================================================================
# GET /history
# ============================================================================

class TestHistory:
    def test_enriches_each_sim(self, client, viewer_user, login_as, monkeypatch):
        sim = _FakeSimState(simulation_id="s1")

        class _M:
            def list_simulations(self):
                return [sim]
            def get_simulation_config(self, _):
                return {
                    "simulation_requirement": "req",
                    "time_config": {"total_simulation_hours": 24, "minutes_per_round": 60},
                }

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)

        class _RunState:
            current_round = 5
            total_rounds = 10
            class runner_status:
                value = "running"

        monkeypatch.setattr(
            crud_routes.SimulationRunner, "get_run_state",
            staticmethod(lambda _: _RunState()),
        )
        monkeypatch.setattr(
            crud_routes.ProjectManager, "get_project",
            staticmethod(lambda _: _FakeProject()),
        )
        monkeypatch.setattr(
            crud_routes,
            "_get_report_id_for_simulation",
            lambda _: "report_42",
        )

        login_as("viewer@test.local")
        resp = client.get("/api/simulation/history?limit=5")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        item = body["data"][0]
        assert item["simulation_requirement"] == "req"
        assert item["total_simulation_hours"] == 24
        assert item["current_round"] == 5
        assert item["total_rounds"] == 10
        assert item["runner_status"] == "running"
        assert item["report_id"] == "report_42"
        assert item["version"] == "v1.0.2"

    def test_no_run_state_falls_back(
        self, client, viewer_user, login_as, monkeypatch
    ):
        sim = _FakeSimState(simulation_id="s1")

        class _M:
            def list_simulations(self):
                return [sim]
            def get_simulation_config(self, _):
                return None

        monkeypatch.setattr(crud_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            crud_routes.SimulationRunner, "get_run_state",
            staticmethod(lambda _: None),
        )
        monkeypatch.setattr(
            crud_routes.ProjectManager, "get_project",
            staticmethod(lambda _: None),
        )
        monkeypatch.setattr(
            crud_routes, "_get_report_id_for_simulation", lambda _: None
        )

        login_as("viewer@test.local")
        resp = client.get("/api/simulation/history")
        body = resp.get_json()
        assert resp.status_code == 200
        item = body["data"][0]
        assert item["current_round"] == 0
        assert item["runner_status"] == "idle"
        assert item["files"] == []
        assert item["report_id"] is None
