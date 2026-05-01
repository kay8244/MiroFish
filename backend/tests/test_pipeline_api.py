"""
Pipeline API 라우트 integration tests (`app/api/pipeline.py`).

라우트 4개:
- POST /api/pipeline/run                  : multipart seed 업로드 + 비동기 run 시작
- GET  /api/pipeline/status/<run_id>      : A3 스키마 상태 (UI polling)
- GET  /api/pipeline/manifest/<run_id>    : Run Manifest JSON
- POST /api/pipeline/resume/<run_id>      : 실패한 run 재개

start_run 의 백그라운드 스레드는 즉시 done.set() 하도록 가짜 함수로 대체해 인라인.
"""

import io
import threading

import pytest

from app.api import pipeline as pipeline_routes
from app.services.pipeline_orchestrator import (
    RunAlreadyCompleted,
    RunCleanupFailed,
    RunNotFound,
    ZepPurgeFailed,
)


# ---------------------------------------------------------------------------
# 가짜 오케스트레이터
# ---------------------------------------------------------------------------

class _FakeOrchestrator:
    def __init__(self):
        self.start_calls = []
        self.resume_calls = []
        self._next_run_id = "run_abc"
        self._start_exc = None
        self._status_exc = None
        self._manifest_exc = None
        self._resume_exc = None
        self._status = {"run_id": "run_abc", "phase": "graph_build"}
        self._manifest = {"run_id": "run_abc", "version": 1}

    def start_run(self, seed_files, assumptions_version, extra_config):
        self.start_calls.append({
            "seed_files": list(seed_files),
            "assumptions_version": assumptions_version,
            "extra_config": extra_config,
        })
        if self._start_exc:
            raise self._start_exc
        return self._next_run_id

    def get_status(self, run_id):
        if self._status_exc:
            raise self._status_exc
        return self._status

    def get_manifest(self, run_id):
        if self._manifest_exc:
            raise self._manifest_exc
        return self._manifest

    def resume_run(self, run_id):
        self.resume_calls.append(run_id)
        if self._resume_exc:
            raise self._resume_exc


@pytest.fixture
def fake_orchestrator(monkeypatch):
    orch = _FakeOrchestrator()
    monkeypatch.setattr(pipeline_routes, "_orchestrator", orch)
    return orch


@pytest.fixture
def inline_thread(monkeypatch):
    """start_run 의 비동기 스레드를 즉시 실행 (테스트 결정성)."""
    real_thread = threading.Thread

    def _factory(target=None, daemon=None, **kw):
        # 즉시 인라인 실행 후 .start() 가 NO-OP 인 객체 반환
        if target is not None:
            target()

        class _Done:
            def start(self_inner):
                pass

        return _Done()

    monkeypatch.setattr(pipeline_routes.threading, "Thread", _factory)


def _txt_upload(content="hello", filename="seed.txt"):
    return (io.BytesIO(content.encode("utf-8")), filename)


# ============================================================================
# 인증 게이트
# ============================================================================

class TestAuthGate:
    @pytest.mark.parametrize("method,path", [
        ("post", "/api/pipeline/run"),
        ("get",  "/api/pipeline/status/r1"),
        ("get",  "/api/pipeline/manifest/r1"),
        ("post", "/api/pipeline/resume/r1"),
    ])
    def test_requires_auth(self, client, method, path):
        fn = getattr(client, method)
        resp = fn(path, json={}) if method == "post" else fn(path)
        assert resp.status_code == 401


class TestWriteRoleGate:
    @pytest.mark.parametrize("path", [
        "/api/pipeline/run",
        "/api/pipeline/resume/r1",
    ])
    def test_viewer_forbidden(self, client, viewer_user, login_as, path):
        login_as("viewer@test.local")
        resp = client.post(path, json={})
        assert resp.status_code == 403


# ============================================================================
# POST /run
# ============================================================================

class TestStartRun:
    def test_missing_seed_files(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/pipeline/run",
            data={"assumptions_version": "v1"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "missing_seed_files"

    def test_invalid_extra_config_json(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/pipeline/run",
            data={
                "seed_files": _txt_upload(),
                "extra_config": "not-json",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "invalid_extra_config"

    def test_extra_config_must_be_object(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/pipeline/run",
            data={
                "seed_files": _txt_upload(),
                "extra_config": "[1,2,3]",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "invalid_extra_config"

    def test_unsupported_format(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/pipeline/run",
            data={"seed_files": (io.BytesIO(b"data"), "image.png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"] == "unsupported_format"

    def test_happy_path(
        self, client, builder_user, login_as, fake_orchestrator, inline_thread
    ):
        login_as("builder@test.local")
        resp = client.post(
            "/api/pipeline/run",
            data={
                "seed_files": _txt_upload(content="seed text"),
                "assumptions_version": "ai_server_si_wafer_v1",
                "extra_config": '{"simulation_max_rounds": 3}',
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["run_id"] == "run_abc"
        assert body["status_url"] == "/api/pipeline/status/run_abc"
        assert len(fake_orchestrator.start_calls) == 1
        call = fake_orchestrator.start_calls[0]
        assert call["assumptions_version"] == "ai_server_si_wafer_v1"
        assert call["extra_config"] == {"simulation_max_rounds": 3}
        assert len(call["seed_files"]) == 1
        assert call["seed_files"][0].name.endswith("seed.txt")

    def test_start_failed_500(
        self, client, builder_user, login_as, fake_orchestrator, inline_thread
    ):
        fake_orchestrator._start_exc = RuntimeError("boom")
        login_as("builder@test.local")
        resp = client.post(
            "/api/pipeline/run",
            data={"seed_files": _txt_upload()},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["error"] == "start_failed"
        assert "boom" in body["message"]

    def test_default_assumptions_version(
        self, client, builder_user, login_as, fake_orchestrator, inline_thread
    ):
        login_as("builder@test.local")
        resp = client.post(
            "/api/pipeline/run",
            data={"seed_files": _txt_upload()},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 202
        # 기본값은 ai_server_si_wafer_v1
        assert (
            fake_orchestrator.start_calls[0]["assumptions_version"]
            == "ai_server_si_wafer_v1"
        )


# ============================================================================
# GET /status/<run_id>
# ============================================================================

class TestGetStatus:
    def test_happy(self, client, viewer_user, login_as, fake_orchestrator):
        fake_orchestrator._status = {
            "run_id": "r1", "phase": "report_generate", "progress": 75
        }
        login_as("viewer@test.local")
        resp = client.get("/api/pipeline/status/r1")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["phase"] == "report_generate"
        assert body["progress"] == 75

    def test_not_found(self, client, viewer_user, login_as, fake_orchestrator):
        fake_orchestrator._status_exc = RunNotFound("r1")
        login_as("viewer@test.local")
        resp = client.get("/api/pipeline/status/r1")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["error"] == "run_not_found"
        assert body["run_id"] == "r1"


# ============================================================================
# GET /manifest/<run_id>
# ============================================================================

class TestGetManifest:
    def test_happy(self, client, viewer_user, login_as, fake_orchestrator):
        fake_orchestrator._manifest = {"run_id": "r1", "schema_version": "a3"}
        login_as("viewer@test.local")
        resp = client.get("/api/pipeline/manifest/r1")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["schema_version"] == "a3"

    def test_not_found(self, client, viewer_user, login_as, fake_orchestrator):
        fake_orchestrator._manifest_exc = RunNotFound("r1")
        login_as("viewer@test.local")
        resp = client.get("/api/pipeline/manifest/r1")
        assert resp.status_code == 404
        assert resp.get_json()["error"] == "run_not_found"


# ============================================================================
# POST /resume/<run_id>
# ============================================================================

class TestResumeRun:
    def test_happy_returns_202(
        self, client, builder_user, login_as, fake_orchestrator, inline_thread
    ):
        login_as("builder@test.local")
        resp = client.post("/api/pipeline/resume/r1")
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["run_id"] == "r1"
        assert body["status_url"] == "/api/pipeline/status/r1"
        assert fake_orchestrator.resume_calls == ["r1"]
