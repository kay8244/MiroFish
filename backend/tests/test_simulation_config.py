"""
시뮬레이션 설정·다운로드 라우트 integration tests (`app/api/simulation/config.py`).

라우트 4개 (모두 GET):
- /api/simulation/<sim_id>/config/realtime  : state.json + simulation_config.json 직접 read
- /api/simulation/<sim_id>/config           : SimulationManager.get_simulation_config 경유
- /api/simulation/<sim_id>/config/download  : send_file
- /api/simulation/script/<script_name>/download : backend/scripts/ send_file (allowlist)

전략:
- realtime 은 파일 기반이라 tmp_path + Config.OASIS_SIMULATION_DATA_DIR monkeypatch
- 나머지 2개는 SimulationManager 클래스를 가짜로 치환
- 스크립트 다운로드는 BACKEND_DIR/scripts 를 tmp_path 로 치환
"""

import json
import os
from pathlib import Path

import pytest

from app.api.simulation import config as config_routes
from app.config import Config


# ---------------------------------------------------------------------------
# 공용 fixture: 가상 시뮬레이션 디렉토리
# ---------------------------------------------------------------------------

@pytest.fixture
def sim_root(tmp_path, monkeypatch):
    """Config.OASIS_SIMULATION_DATA_DIR 를 tmp_path 의 가상 루트로 치환."""
    root = tmp_path / "oasis_sims"
    root.mkdir()
    monkeypatch.setattr(Config, "OASIS_SIMULATION_DATA_DIR", str(root))
    return root


def _write_state(sim_dir: Path, **kwargs):
    sim_dir.mkdir(parents=True, exist_ok=True)
    (sim_dir / "state.json").write_text(json.dumps(kwargs), encoding="utf-8")


def _write_config(sim_dir: Path, payload: dict):
    sim_dir.mkdir(parents=True, exist_ok=True)
    (sim_dir / "simulation_config.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# ============================================================================
# 인증 게이트
# ============================================================================

class TestAuthGate:
    def test_realtime_requires_auth(self, client):
        assert client.get("/api/simulation/sim_x/config/realtime").status_code == 401

    def test_config_requires_auth(self, client):
        assert client.get("/api/simulation/sim_x/config").status_code == 401

    def test_download_requires_auth(self, client):
        assert client.get("/api/simulation/sim_x/config/download").status_code == 401

    def test_script_requires_auth(self, client):
        assert client.get("/api/simulation/script/run_twitter_simulation.py/download").status_code == 401


# ============================================================================
# GET /<sim_id>/config/realtime
# ============================================================================

class TestRealtimeConfig:
    def test_missing_simulation_404(self, client, sim_root, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/no_such_sim/config/realtime")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["success"] is False
        assert "no_such_sim" in body["error"]

    def test_dir_exists_but_no_config_file(self, client, sim_root, viewer_user, login_as):
        sim_id = "sim_a"
        (sim_root / sim_id).mkdir()
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/config/realtime")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["simulation_id"] == sim_id
        assert data["file_exists"] is False
        assert data["config"] is None
        assert data["is_generating"] is False

    def test_with_config_emits_summary(self, client, sim_root, viewer_user, login_as):
        sim_id = "sim_b"
        sim_dir = sim_root / sim_id
        _write_config(sim_dir, {
            "agent_configs": [{}, {}, {}],
            "time_config": {"total_simulation_hours": 24},
            "event_config": {
                "initial_posts": [{}, {}],
                "hot_topics": [{}],
            },
            "twitter_config": {"x": 1},
            "generated_at": "2026-04-30T00:00:00",
            "llm_model": "gpt-4o",
        })
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/config/realtime")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["file_exists"] is True
        assert data["file_modified_at"] is not None
        s = data["summary"]
        assert s["total_agents"] == 3
        assert s["simulation_hours"] == 24
        assert s["initial_posts_count"] == 2
        assert s["hot_topics_count"] == 1
        assert s["has_twitter_config"] is True
        assert s["has_reddit_config"] is False
        assert s["llm_model"] == "gpt-4o"

    def test_state_preparing_marks_is_generating(self, client, sim_root, viewer_user, login_as):
        sim_id = "sim_c"
        sim_dir = sim_root / sim_id
        sim_dir.mkdir()
        _write_state(sim_dir, status="preparing", profiles_generated=True)
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/config/realtime")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["is_generating"] is True
        assert data["generation_stage"] == "generating_config"

    def test_state_preparing_profiles_phase(self, client, sim_root, viewer_user, login_as):
        sim_id = "sim_d"
        sim_dir = sim_root / sim_id
        sim_dir.mkdir()
        _write_state(sim_dir, status="preparing", profiles_generated=False)
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/config/realtime")
        data = resp.get_json()["data"]
        assert data["is_generating"] is True
        assert data["generation_stage"] == "generating_profiles"

    def test_state_ready_completed(self, client, sim_root, viewer_user, login_as):
        sim_id = "sim_e"
        sim_dir = sim_root / sim_id
        sim_dir.mkdir()
        _write_state(sim_dir, status="ready", config_generated=True)
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/config/realtime")
        data = resp.get_json()["data"]
        assert data["is_generating"] is False
        assert data["generation_stage"] == "completed"
        assert data["config_generated"] is True

    def test_corrupted_config_json_does_not_500(
        self, client, sim_root, viewer_user, login_as
    ):
        """쓰기 중인 부분 JSON 도 graceful — config=None, file_exists=True."""
        sim_id = "sim_f"
        sim_dir = sim_root / sim_id
        sim_dir.mkdir()
        (sim_dir / "simulation_config.json").write_text("{not valid", encoding="utf-8")
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/{sim_id}/config/realtime")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["file_exists"] is True
        assert data["config"] is None


# ============================================================================
# GET /<sim_id>/config
# ============================================================================

class TestGetConfig:
    def test_returns_config(self, client, viewer_user, login_as, monkeypatch):
        captured = {}

        class _FakeManager:
            def get_simulation_config(self, sim_id):
                captured["sim_id"] = sim_id
                return {"agent_configs": [], "echo": sim_id}

        monkeypatch.setattr(config_routes, "SimulationManager", _FakeManager)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/config")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["echo"] == "sim_x"
        assert captured["sim_id"] == "sim_x"

    def test_missing_returns_404(self, client, viewer_user, login_as, monkeypatch):
        class _FakeManager:
            def get_simulation_config(self, sim_id):
                return None

        monkeypatch.setattr(config_routes, "SimulationManager", _FakeManager)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/config")
        assert resp.status_code == 404
        assert resp.get_json()["success"] is False

    def test_manager_exception_500(self, client, viewer_user, login_as, monkeypatch):
        class _FakeManager:
            def get_simulation_config(self, sim_id):
                raise RuntimeError("db down")

        monkeypatch.setattr(config_routes, "SimulationManager", _FakeManager)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/config")
        assert resp.status_code == 500
        assert "db down" in resp.get_json()["error"]


# ============================================================================
# GET /<sim_id>/config/download
# ============================================================================

class TestDownloadConfig:
    def test_sends_file_when_exists(
        self, client, tmp_path, viewer_user, login_as, monkeypatch
    ):
        sim_dir = tmp_path / "sim_dl"
        sim_dir.mkdir()
        payload = {"k": "v"}
        (sim_dir / "simulation_config.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        class _FakeManager:
            def _get_simulation_dir(self, sim_id):
                return str(sim_dir)

        monkeypatch.setattr(config_routes, "SimulationManager", _FakeManager)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_dl/config/download")
        assert resp.status_code == 200
        # send_file 은 attachment header + JSON 내용
        cd = resp.headers.get("Content-Disposition", "")
        assert "simulation_config.json" in cd
        assert json.loads(resp.data.decode("utf-8")) == payload

    def test_404_when_missing(
        self, client, tmp_path, viewer_user, login_as, monkeypatch
    ):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        class _FakeManager:
            def _get_simulation_dir(self, sim_id):
                return str(empty_dir)

        monkeypatch.setattr(config_routes, "SimulationManager", _FakeManager)
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/sim_x/config/download")
        assert resp.status_code == 404
        assert resp.get_json()["success"] is False


# ============================================================================
# GET /script/<script_name>/download
# ============================================================================

class TestDownloadScript:
    @pytest.fixture
    def fake_scripts_dir(self, tmp_path, monkeypatch):
        d = tmp_path / "fake_backend"
        scripts = d / "scripts"
        scripts.mkdir(parents=True)
        # allowlist 4종 모두 존재하게 미리 만들지 않고, 케이스별로 생성
        monkeypatch.setattr(config_routes, "BACKEND_DIR", str(d))
        return scripts

    def test_unknown_script_400(
        self, client, fake_scripts_dir, viewer_user, login_as
    ):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/script/evil.sh/download")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert "evil.sh" in body["error"]

    def test_path_traversal_blocked(
        self, client, fake_scripts_dir, viewer_user, login_as
    ):
        """Path traversal 시도가 핸들러 통과 후 외부 파일을 노출하지 않아야 함.

        Flask 가 `..%2F` 를 디코드하면 라우트 매칭 단계에서 404, allowlist 까지
        도달해도 400. 어느 경로든 200(파일 전송)/500(서버 에러)가 아니어야 한다.
        """
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/script/..%2Fetc%2Fpasswd/download")
        assert resp.status_code in (400, 404)

    def test_allowed_but_missing_404(
        self, client, fake_scripts_dir, viewer_user, login_as
    ):
        login_as("viewer@test.local")
        resp = client.get("/api/simulation/script/run_twitter_simulation.py/download")
        assert resp.status_code == 404
        assert resp.get_json()["success"] is False

    @pytest.mark.parametrize("script_name", [
        "run_twitter_simulation.py",
        "run_reddit_simulation.py",
        "run_parallel_simulation.py",
        "action_logger.py",
    ])
    def test_allowed_script_downloads(
        self, client, fake_scripts_dir, viewer_user, login_as, script_name
    ):
        body = f"# {script_name}\nprint('hi')\n"
        (fake_scripts_dir / script_name).write_text(body, encoding="utf-8")
        login_as("viewer@test.local")
        resp = client.get(f"/api/simulation/script/{script_name}/download")
        assert resp.status_code == 200
        assert script_name in resp.headers.get("Content-Disposition", "")
        assert resp.data.decode("utf-8") == body
