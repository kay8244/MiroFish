"""
Report API 라우트 integration tests (`app/api/report.py`).

라우트 18개:
- POST /api/report/generate                       : 비동기 보고서 생성 (background thread)
- POST /api/report/generate/status                : 태스크 진행 상황 / 완료 단축
- GET  /api/report/<report_id>                    : 보고서 상세
- GET  /api/report/by-simulation/<simulation_id>  : 시뮬레이션으로 조회
- GET  /api/report/list                           : 보고서 목록 (필터/limit)
- GET  /api/report/<report_id>/download           : Markdown 다운로드 (파일 또는 임시)
- DELETE /api/report/<report_id>                  : 보고서 삭제
- POST /api/report/chat                           : Report Agent 와 대화
- GET  /api/report/<report_id>/progress           : 생성 진행 상황
- GET  /api/report/<report_id>/sections           : 생성된 섹션 목록
- GET  /api/report/<report_id>/section/<idx>      : 단일 섹션 내용
- GET  /api/report/check/<simulation_id>          : 보고서 존재 여부 / interview 잠금 해제
- GET  /api/report/<report_id>/agent-log          : 구조화 로그 (증분)
- GET  /api/report/<report_id>/agent-log/stream   : 구조화 로그 (전체)
- GET  /api/report/<report_id>/console-log        : 콘솔 로그 (증분)
- GET  /api/report/<report_id>/console-log/stream : 콘솔 로그 (전체)
- POST /api/report/tools/search                   : 그래프 검색 도구
- POST /api/report/tools/statistics               : 그래프 통계 도구

generate 의 백그라운드 스레드는 threading.Thread 를 monkeypatch 해 인라인 차단.
"""

import os

import pytest

from app.api import report as report_routes
from app.services.report_agent import ReportStatus
from app.services.simulation_manager import SimulationStatus
from app.utils.rate_limiter import _limiter as _rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
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


class _FakeReport:
    def __init__(
        self,
        report_id="report_abc",
        simulation_id="sim_1",
        status=ReportStatus.COMPLETED,
        markdown_content="# 보고서\n\n본문",
    ):
        self.report_id = report_id
        self.simulation_id = simulation_id
        self.status = status
        self.markdown_content = markdown_content

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "markdown_content": self.markdown_content,
        }


class _FakeTask:
    def __init__(self, task_id="task_1", status="processing", progress=42, message="..."):
        self.task_id = task_id
        self.status = status
        self.progress = progress
        self.message = message

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
        }


@pytest.fixture
def block_threads(monkeypatch):
    """generate 의 백그라운드 스레드를 NO-OP 으로."""
    class _NoopThread:
        def __init__(self, **kw):
            pass
        def start(self):
            pass
    monkeypatch.setattr(report_routes.threading, "Thread", _NoopThread)


# ============================================================================
# 인증 게이트 (전역 before_request)
# ============================================================================

class TestAuthGate:
    @pytest.mark.parametrize("method,path", [
        ("post", "/api/report/generate"),
        ("post", "/api/report/generate/status"),
        ("get",  "/api/report/report_x"),
        ("get",  "/api/report/by-simulation/sim_x"),
        ("get",  "/api/report/list"),
        ("get",  "/api/report/report_x/download"),
        ("delete", "/api/report/report_x"),
        ("post", "/api/report/chat"),
        ("get",  "/api/report/report_x/progress"),
        ("get",  "/api/report/report_x/sections"),
        ("get",  "/api/report/report_x/section/1"),
        ("get",  "/api/report/check/sim_x"),
        ("get",  "/api/report/report_x/agent-log"),
        ("get",  "/api/report/report_x/agent-log/stream"),
        ("get",  "/api/report/report_x/console-log"),
        ("get",  "/api/report/report_x/console-log/stream"),
        ("post", "/api/report/tools/search"),
        ("post", "/api/report/tools/statistics"),
    ])
    def test_requires_auth(self, client, method, path):
        fn = getattr(client, method)
        resp = fn(path, json={}) if method in ("post",) else fn(path)
        assert resp.status_code == 401


# ============================================================================
# 쓰기 메서드 — viewer 는 403
# ============================================================================

class TestWriteRoleGate:
    @pytest.mark.parametrize("method,path,payload", [
        ("post",   "/api/report/generate",        {"simulation_id": "s"}),
        ("delete", "/api/report/report_x",        None),
        ("post",   "/api/report/chat",            {"simulation_id": "s", "message": "hi"}),
        ("post",   "/api/report/tools/search",    {"graph_id": "g", "query": "q"}),
        ("post",   "/api/report/tools/statistics", {"graph_id": "g"}),
    ])
    def test_viewer_forbidden(self, client, viewer_user, login_as, method, path, payload):
        login_as("viewer@test.local")
        fn = getattr(client, method)
        resp = fn(path, json=payload) if payload is not None else fn(path)
        assert resp.status_code == 403


# ============================================================================
# POST /generate
# ============================================================================

class TestGenerate:
    def test_missing_simulation_id(self, client, builder_user, login_as, block_threads):
        login_as("builder@test.local")
        resp = client.post("/api/report/generate", json={})
        assert resp.status_code == 400
        assert "simulation_id" in resp.get_json()["error"]

    def test_unknown_simulation_404(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return None
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        login_as("builder@test.local")
        resp = client.post("/api/report/generate", json={"simulation_id": "ghost"})
        assert resp.status_code == 404

    def test_existing_completed_short_circuits(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState()
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report_by_simulation",
            staticmethod(lambda _: _FakeReport(report_id="report_old")),
        )
        login_as("builder@test.local")
        resp = client.post("/api/report/generate", json={"simulation_id": "sim_1"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["already_generated"] is True
        assert body["data"]["report_id"] == "report_old"
        assert body["data"]["status"] == "completed"

    def test_no_project_404(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState()
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report_by_simulation",
            staticmethod(lambda _: None),
        )
        monkeypatch.setattr(
            report_routes.ProjectManager, "get_project", staticmethod(lambda _: None)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/report/generate",
            json={"simulation_id": "sim_1", "force_regenerate": True},
        )
        assert resp.status_code == 404

    def test_no_graph_id_400(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState(graph_id=None)
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            report_routes.ReportManager, "get_report_by_simulation", staticmethod(lambda _: None)
        )
        monkeypatch.setattr(
            report_routes.ProjectManager,
            "get_project",
            staticmethod(lambda _: _FakeProject(graph_id=None)),
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/report/generate",
            json={"simulation_id": "sim_1", "force_regenerate": True},
        )
        assert resp.status_code == 400
        assert "그래프" in resp.get_json()["error"]

    def test_no_simulation_requirement_400(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState(simulation_requirement=None)
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            report_routes.ReportManager, "get_report_by_simulation", staticmethod(lambda _: None)
        )
        monkeypatch.setattr(
            report_routes.ProjectManager,
            "get_project",
            staticmethod(lambda _: _FakeProject(simulation_requirement=None)),
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/report/generate",
            json={"simulation_id": "sim_1", "force_regenerate": True},
        )
        assert resp.status_code == 400
        assert "요구사항" in resp.get_json()["error"]

    def test_happy_path_starts_task(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState()
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            report_routes.ReportManager, "get_report_by_simulation", staticmethod(lambda _: None)
        )
        monkeypatch.setattr(
            report_routes.ProjectManager, "get_project", staticmethod(lambda _: _FakeProject())
        )

        captured = {}

        class _TM:
            def create_task(self, **kw):
                captured.update(kw)
                return "task_99"
            def update_task(self, *a, **kw):
                pass
            def complete_task(self, *a, **kw):
                pass
            def fail_task(self, *a, **kw):
                pass

        monkeypatch.setattr(report_routes, "TaskManager", _TM)
        login_as("builder@test.local")
        resp = client.post("/api/report/generate", json={"simulation_id": "sim_1"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["task_id"] == "task_99"
        assert body["data"]["status"] == "generating"
        assert body["data"]["already_generated"] is False
        assert body["data"]["report_id"].startswith("report_")
        assert captured["task_type"] == "report_generate"
        assert captured["metadata"]["simulation_id"] == "sim_1"

    def test_rate_limit_exceeded(
        self, client, builder_user, login_as, block_threads, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState()
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            report_routes.ReportManager, "get_report_by_simulation", staticmethod(lambda _: None)
        )
        monkeypatch.setattr(
            report_routes.ProjectManager, "get_project", staticmethod(lambda _: _FakeProject())
        )

        class _TM:
            def create_task(self, **kw):
                return "task_x"
            def update_task(self, *a, **kw):
                pass
            def complete_task(self, *a, **kw):
                pass
            def fail_task(self, *a, **kw):
                pass

        monkeypatch.setattr(report_routes, "TaskManager", _TM)
        login_as("builder@test.local")
        # max_requests=3, period=60s — 4번째는 429
        for _ in range(3):
            r = client.post("/api/report/generate", json={"simulation_id": "sim_1"})
            assert r.status_code == 200
        r4 = client.post("/api/report/generate", json={"simulation_id": "sim_1"})
        assert r4.status_code == 429


# ============================================================================
# POST /generate/status
# ============================================================================

class TestGenerateStatus:
    def test_missing_both_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/report/generate/status", json={})
        assert resp.status_code == 400

    def test_simulation_id_completed_shortcut(
        self, client, builder_user, login_as, monkeypatch
    ):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report_by_simulation",
            staticmethod(lambda _: _FakeReport(report_id="report_done")),
        )
        login_as("builder@test.local")
        resp = client.post("/api/report/generate/status", json={"simulation_id": "sim_1"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["already_completed"] is True
        assert body["data"]["report_id"] == "report_done"

    def test_unknown_task_id_404(
        self, client, builder_user, login_as, monkeypatch
    ):
        monkeypatch.setattr(
            report_routes.ReportManager, "get_report_by_simulation", staticmethod(lambda _: None)
        )

        class _TM:
            def get_task(self, _):
                return None
        monkeypatch.setattr(report_routes, "TaskManager", _TM)
        login_as("builder@test.local")
        resp = client.post("/api/report/generate/status", json={"task_id": "ghost"})
        assert resp.status_code == 404

    def test_task_in_progress_returns_dict(
        self, client, builder_user, login_as, monkeypatch
    ):
        class _TM:
            def get_task(self, _):
                return _FakeTask()
        monkeypatch.setattr(report_routes, "TaskManager", _TM)
        login_as("builder@test.local")
        resp = client.post("/api/report/generate/status", json={"task_id": "task_1"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["task_id"] == "task_1"
        assert body["data"]["progress"] == 42


# ============================================================================
# GET /<report_id>
# ============================================================================

class TestGetReport:
    def test_happy(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report",
            staticmethod(lambda rid: _FakeReport(report_id=rid)),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_xyz")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["report_id"] == "report_xyz"

    def test_not_found(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager, "get_report", staticmethod(lambda _: None)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/missing")
        assert resp.status_code == 404


# ============================================================================
# GET /by-simulation/<sim_id>
# ============================================================================

class TestGetReportBySimulation:
    def test_happy(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report_by_simulation",
            staticmethod(lambda sid: _FakeReport(simulation_id=sid)),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/by-simulation/sim_42")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["has_report"] is True
        assert body["data"]["simulation_id"] == "sim_42"

    def test_not_found(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report_by_simulation",
            staticmethod(lambda _: None),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/by-simulation/missing")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["has_report"] is False


# ============================================================================
# GET /list
# ============================================================================

class TestListReports:
    def test_returns_all(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        def _list(simulation_id=None, limit=50):
            captured["simulation_id"] = simulation_id
            captured["limit"] = limit
            return [_FakeReport(report_id=f"r{i}") for i in range(3)]

        monkeypatch.setattr(
            report_routes.ReportManager, "list_reports", staticmethod(_list)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/list")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 3
        assert captured["simulation_id"] is None
        assert captured["limit"] == 50

    def test_with_filter_and_limit(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        def _list(simulation_id=None, limit=50):
            captured["simulation_id"] = simulation_id
            captured["limit"] = limit
            return []

        monkeypatch.setattr(
            report_routes.ReportManager, "list_reports", staticmethod(_list)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/list?simulation_id=sim_1&limit=5")
        assert resp.status_code == 200
        assert captured["simulation_id"] == "sim_1"
        assert captured["limit"] == 5


# ============================================================================
# GET /<report_id>/download
# ============================================================================

class TestDownloadReport:
    def test_not_found(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager, "get_report", staticmethod(lambda _: None)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/missing/download")
        assert resp.status_code == 404

    def test_with_md_file(self, client, viewer_user, login_as, monkeypatch, tmp_path):
        md_file = tmp_path / "report_a.md"
        md_file.write_text("# 보고서\n", encoding="utf-8")
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report",
            staticmethod(lambda _: _FakeReport()),
        )
        monkeypatch.setattr(
            report_routes.ReportManager,
            "_get_report_markdown_path",
            staticmethod(lambda _: str(md_file)),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_a/download")
        assert resp.status_code == 200
        assert resp.headers["Content-Disposition"].startswith("attachment")

    def test_without_md_file_uses_temp(
        self, client, viewer_user, login_as, monkeypatch, tmp_path
    ):
        ghost_path = str(tmp_path / "no.md")
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report",
            staticmethod(lambda _: _FakeReport(markdown_content="# from memory")),
        )
        monkeypatch.setattr(
            report_routes.ReportManager,
            "_get_report_markdown_path",
            staticmethod(lambda _: ghost_path),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/download")
        assert resp.status_code == 200


# ============================================================================
# DELETE /<report_id>
# ============================================================================

class TestDeleteReport:
    def test_happy(self, client, builder_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager, "delete_report", staticmethod(lambda _: True)
        )
        login_as("builder@test.local")
        resp = client.delete("/api/report/report_x")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_not_found(self, client, builder_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager, "delete_report", staticmethod(lambda _: False)
        )
        login_as("builder@test.local")
        resp = client.delete("/api/report/missing")
        assert resp.status_code == 404


# ============================================================================
# POST /chat
# ============================================================================

class TestChat:
    def test_missing_simulation_id(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/report/chat", json={"message": "hi"})
        assert resp.status_code == 400

    def test_missing_message(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/report/chat", json={"simulation_id": "s"})
        assert resp.status_code == 400

    def test_unknown_simulation_404(
        self, client, builder_user, login_as, monkeypatch
    ):
        class _M:
            def get_simulation(self, _):
                return None
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        login_as("builder@test.local")
        resp = client.post(
            "/api/report/chat", json={"simulation_id": "ghost", "message": "hi"}
        )
        assert resp.status_code == 404

    def test_no_project_404(self, client, builder_user, login_as, monkeypatch):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState()
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            report_routes.ProjectManager, "get_project", staticmethod(lambda _: None)
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/report/chat", json={"simulation_id": "sim_1", "message": "hi"}
        )
        assert resp.status_code == 404

    def test_no_graph_400(self, client, builder_user, login_as, monkeypatch):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState(graph_id=None)
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            report_routes.ProjectManager,
            "get_project",
            staticmethod(lambda _: _FakeProject(graph_id=None)),
        )
        login_as("builder@test.local")
        resp = client.post(
            "/api/report/chat", json={"simulation_id": "sim_1", "message": "hi"}
        )
        assert resp.status_code == 400

    def test_happy_path(self, client, builder_user, login_as, monkeypatch):
        class _M:
            def get_simulation(self, _):
                return _FakeSimState()
        monkeypatch.setattr(report_routes, "SimulationManager", _M)
        monkeypatch.setattr(
            report_routes.ProjectManager,
            "get_project",
            staticmethod(lambda _: _FakeProject()),
        )

        captured = {}

        class _Agent:
            def __init__(self, **kw):
                captured["init"] = kw
            def chat(self, message, chat_history):
                captured["message"] = message
                captured["history"] = chat_history
                return {"response": "안녕하세요", "tool_calls": [], "sources": []}

        monkeypatch.setattr(report_routes, "ReportAgent", _Agent)
        login_as("builder@test.local")
        resp = client.post(
            "/api/report/chat",
            json={
                "simulation_id": "sim_1",
                "message": "여론 동향?",
                "chat_history": [{"role": "user", "content": "이전"}],
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["response"] == "안녕하세요"
        assert captured["init"]["graph_id"] == "g1"
        assert captured["init"]["simulation_id"] == "sim_1"
        assert captured["message"] == "여론 동향?"
        assert captured["history"] == [{"role": "user", "content": "이전"}]


# ============================================================================
# GET /<report_id>/progress
# ============================================================================

class TestReportProgress:
    def test_happy(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_progress",
            staticmethod(lambda _: {"status": "generating", "progress": 30}),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/progress")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["progress"] == 30

    def test_not_found(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager, "get_progress", staticmethod(lambda _: None)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/missing/progress")
        assert resp.status_code == 404


# ============================================================================
# GET /<report_id>/sections
# ============================================================================

class TestReportSections:
    def test_with_completed_report(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_generated_sections",
            staticmethod(lambda _: [{"filename": "section_01.md", "section_index": 1}]),
        )
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report",
            staticmethod(lambda _: _FakeReport(status=ReportStatus.COMPLETED)),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/sections")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["total_sections"] == 1
        assert body["data"]["is_complete"] is True

    def test_without_report(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_generated_sections",
            staticmethod(lambda _: []),
        )
        monkeypatch.setattr(
            report_routes.ReportManager, "get_report", staticmethod(lambda _: None)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/no_report/sections")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["is_complete"] is False
        assert body["data"]["total_sections"] == 0


# ============================================================================
# GET /<report_id>/section/<int:idx>
# ============================================================================

class TestSingleSection:
    def test_not_found(self, client, viewer_user, login_as, monkeypatch, tmp_path):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "_get_section_path",
            staticmethod(lambda rid, idx: str(tmp_path / "ghost.md")),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/section/5")
        assert resp.status_code == 404

    def test_happy(self, client, viewer_user, login_as, monkeypatch, tmp_path):
        sec = tmp_path / "section_02.md"
        sec.write_text("## 본문\n내용", encoding="utf-8")
        monkeypatch.setattr(
            report_routes.ReportManager,
            "_get_section_path",
            staticmethod(lambda rid, idx: str(sec)),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/section/2")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["filename"] == "section_02.md"
        assert "내용" in body["data"]["content"]


# ============================================================================
# GET /check/<simulation_id>
# ============================================================================

class TestCheckReportStatus:
    def test_no_report(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report_by_simulation",
            staticmethod(lambda _: None),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/check/sim_x")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["has_report"] is False
        assert body["data"]["interview_unlocked"] is False

    def test_completed_unlocks_interview(
        self, client, viewer_user, login_as, monkeypatch
    ):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report_by_simulation",
            staticmethod(
                lambda _: _FakeReport(report_id="r_done", status=ReportStatus.COMPLETED)
            ),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/check/sim_x")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["has_report"] is True
        assert body["data"]["report_status"] == ReportStatus.COMPLETED.value
        assert body["data"]["interview_unlocked"] is True

    def test_in_progress_does_not_unlock(
        self, client, viewer_user, login_as, monkeypatch
    ):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_report_by_simulation",
            staticmethod(
                lambda _: _FakeReport(status=ReportStatus.GENERATING)
                if hasattr(ReportStatus, "GENERATING")
                else _FakeReport(status=ReportStatus.PROCESSING)
                if hasattr(ReportStatus, "PROCESSING")
                else _FakeReport(status=ReportStatus.PENDING)
            ),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/check/sim_x")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["has_report"] is True
        assert body["data"]["interview_unlocked"] is False


# ============================================================================
# GET /<report_id>/agent-log [+ /stream]
# ============================================================================

class TestAgentLog:
    def test_default_from_line(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        def _get_log(rid, from_line=0):
            captured["rid"] = rid
            captured["from_line"] = from_line
            return {"logs": [], "total_lines": 0, "from_line": from_line, "has_more": False}

        monkeypatch.setattr(
            report_routes.ReportManager, "get_agent_log", staticmethod(_get_log)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/agent-log")
        assert resp.status_code == 200
        assert captured["from_line"] == 0
        assert captured["rid"] == "report_x"

    def test_with_from_line(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        def _get_log(rid, from_line=0):
            captured["from_line"] = from_line
            return {"logs": [], "total_lines": 0, "from_line": from_line, "has_more": False}

        monkeypatch.setattr(
            report_routes.ReportManager, "get_agent_log", staticmethod(_get_log)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/agent-log?from_line=10")
        assert resp.status_code == 200
        assert captured["from_line"] == 10

    def test_stream(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_agent_log_stream",
            staticmethod(lambda _: [{"action": "start"}, {"action": "done"}]),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/agent-log/stream")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["count"] == 2


# ============================================================================
# GET /<report_id>/console-log [+ /stream]
# ============================================================================

class TestConsoleLog:
    def test_default(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        def _get_log(rid, from_line=0):
            captured["from_line"] = from_line
            return {"logs": [], "total_lines": 0, "from_line": from_line, "has_more": False}

        monkeypatch.setattr(
            report_routes.ReportManager, "get_console_log", staticmethod(_get_log)
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/console-log?from_line=7")
        assert resp.status_code == 200
        assert captured["from_line"] == 7

    def test_stream(self, client, viewer_user, login_as, monkeypatch):
        monkeypatch.setattr(
            report_routes.ReportManager,
            "get_console_log_stream",
            staticmethod(lambda _: ["[INFO] line1", "[INFO] line2", "[INFO] line3"]),
        )
        login_as("viewer@test.local")
        resp = client.get("/api/report/report_x/console-log/stream")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["count"] == 3


# ============================================================================
# POST /tools/search
# ============================================================================

class TestToolsSearch:
    def test_missing_graph_id(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/report/tools/search", json={"query": "q"})
        assert resp.status_code == 400

    def test_missing_query(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/report/tools/search", json={"graph_id": "g"})
        assert resp.status_code == 400

    def test_happy(self, client, builder_user, login_as, monkeypatch):
        captured = {}

        class _Result:
            def to_dict(self):
                return {"hits": []}

        class _Tools:
            def search_graph(self, **kw):
                captured.update(kw)
                return _Result()

        import app.services.graphiti_tools as gt_mod
        monkeypatch.setattr(gt_mod, "GraphitiToolsService", _Tools)
        login_as("builder@test.local")
        resp = client.post(
            "/api/report/tools/search",
            json={"graph_id": "g_1", "query": "AI 서버", "limit": 5},
        )
        assert resp.status_code == 200
        assert captured["graph_id"] == "g_1"
        assert captured["query"] == "AI 서버"
        assert captured["limit"] == 5


# ============================================================================
# POST /tools/statistics
# ============================================================================

class TestToolsStatistics:
    def test_missing_graph_id(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/report/tools/statistics", json={})
        assert resp.status_code == 400

    def test_happy(self, client, builder_user, login_as, monkeypatch):
        captured = {}

        class _Tools:
            def get_graph_statistics(self, graph_id):
                captured["graph_id"] = graph_id
                return {"node_count": 42}

        import app.services.graphiti_tools as gt_mod
        monkeypatch.setattr(gt_mod, "GraphitiToolsService", _Tools)
        login_as("builder@test.local")
        resp = client.post("/api/report/tools/statistics", json={"graph_id": "g_2"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["node_count"] == 42
        assert captured["graph_id"] == "g_2"
