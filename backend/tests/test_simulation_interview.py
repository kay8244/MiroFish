"""
시뮬레이션 인터뷰 라우트 integration tests (`app/api/simulation/interview.py`).

라우트 4개 (모두 POST):
- /interview         : 단일 Agent 인터뷰
- /interview/batch   : 일괄 인터뷰
- /interview/all     : 전체 Agent 인터뷰
- /interview/history : Interview 히스토리 조회
"""

import pytest

from app.api.simulation import interview as interview_routes
from app.api.simulation._shared import INTERVIEW_PROMPT_PREFIX


@pytest.fixture
def fake_runner(monkeypatch):
    """SimulationRunner 의 인터뷰 관련 메서드 치환."""
    state = {"calls": [], "alive": True}

    class _R:
        @staticmethod
        def check_env_alive(simulation_id):
            state["calls"].append(("alive", simulation_id))
            return state["alive"]

        @staticmethod
        def interview_agent(**kw):
            state["calls"].append(("interview_agent", kw))
            return {"success": True, "response": "hi", **kw}

        @staticmethod
        def interview_agents_batch(**kw):
            state["calls"].append(("batch", kw))
            return {"success": True, "interviews_count": len(kw.get("interviews", [])), **{k: v for k, v in kw.items() if k != "interviews"}}

        @staticmethod
        def interview_all_agents(**kw):
            state["calls"].append(("all", kw))
            return {"success": True, **kw}

        @staticmethod
        def get_interview_history(**kw):
            state["calls"].append(("history", kw))
            return [{"agent_id": 0, "response": "x"}, {"agent_id": 1, "response": "y"}]

    monkeypatch.setattr(interview_routes, "SimulationRunner", _R)
    return state


# ============================================================================
# 인증 게이트
# ============================================================================

class TestAuthGate:
    @pytest.mark.parametrize("path", [
        "/api/simulation/interview",
        "/api/simulation/interview/batch",
        "/api/simulation/interview/all",
        "/api/simulation/interview/history",
    ])
    def test_requires_auth(self, client, path):
        assert client.post(path, json={}).status_code == 401


# ============================================================================
# POST /interview
# ============================================================================

class TestInterviewSingle:
    def test_missing_sim_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/interview", json={})
        assert resp.status_code == 400

    def test_missing_agent_id_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview",
            json={"simulation_id": "sim_x", "prompt": "hi"},
        )
        assert resp.status_code == 400
        assert "agent_id" in resp.get_json()["error"]

    def test_missing_prompt_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview",
            json={"simulation_id": "sim_x", "agent_id": 0},
        )
        assert resp.status_code == 400
        assert "prompt" in resp.get_json()["error"]

    def test_invalid_platform_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview",
            json={
                "simulation_id": "sim_x",
                "agent_id": 0,
                "prompt": "hi",
                "platform": "facebook",
            },
        )
        assert resp.status_code == 400

    def test_env_dead_400(self, client, builder_user, login_as, fake_runner):
        fake_runner["alive"] = False
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview",
            json={"simulation_id": "sim_x", "agent_id": 0, "prompt": "hi"},
        )
        assert resp.status_code == 400
        assert "환경" in resp.get_json()["error"]

    def test_happy_path_with_prompt_optimized(
        self, client, builder_user, login_as, fake_runner
    ):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview",
            json={
                "simulation_id": "sim_x",
                "agent_id": 5,
                "prompt": "이 사건에 대해?",
                "platform": "twitter",
                "timeout": 30,
            },
        )
        assert resp.status_code == 200
        # interview_agent 호출 시 prompt 가 PREFIX 로 시작
        call = [c for c in fake_runner["calls"] if c[0] == "interview_agent"][-1]
        kw = call[1]
        assert kw["agent_id"] == 5
        assert kw["platform"] == "twitter"
        assert kw["timeout"] == 30
        assert kw["prompt"].startswith(INTERVIEW_PROMPT_PREFIX)
        assert "이 사건에 대해?" in kw["prompt"]

    def test_timeout_returns_504(self, client, builder_user, login_as, monkeypatch):
        class _R:
            @staticmethod
            def check_env_alive(_):
                return True
            @staticmethod
            def interview_agent(**kw):
                raise TimeoutError("slow")

        monkeypatch.setattr(interview_routes, "SimulationRunner", _R)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview",
            json={"simulation_id": "s", "agent_id": 0, "prompt": "hi"},
        )
        assert resp.status_code == 504

    def test_viewer_post_forbidden(self, client, viewer_user, login_as):
        login_as("viewer@test.local")
        resp = client.post(
            "/api/simulation/interview",
            json={"simulation_id": "s", "agent_id": 0, "prompt": "hi"},
        )
        assert resp.status_code == 403


# ============================================================================
# POST /interview/batch
# ============================================================================

class TestInterviewBatch:
    def test_missing_sim_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/interview/batch", json={})
        assert resp.status_code == 400

    def test_interviews_not_list_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/batch",
            json={"simulation_id": "s", "interviews": "not-a-list"},
        )
        assert resp.status_code == 400

    def test_item_missing_agent_id(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/batch",
            json={
                "simulation_id": "s",
                "interviews": [{"prompt": "hi"}],
            },
        )
        assert resp.status_code == 400
        assert "agent_id" in resp.get_json()["error"]

    def test_item_missing_prompt(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/batch",
            json={
                "simulation_id": "s",
                "interviews": [{"agent_id": 0}],
            },
        )
        assert resp.status_code == 400
        assert "prompt" in resp.get_json()["error"]

    def test_item_invalid_platform(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/batch",
            json={
                "simulation_id": "s",
                "interviews": [{"agent_id": 0, "prompt": "hi", "platform": "tiktok"}],
            },
        )
        assert resp.status_code == 400

    def test_top_level_invalid_platform(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/batch",
            json={
                "simulation_id": "s",
                "interviews": [{"agent_id": 0, "prompt": "hi"}],
                "platform": "tiktok",
            },
        )
        assert resp.status_code == 400

    def test_env_dead(self, client, builder_user, login_as, fake_runner):
        fake_runner["alive"] = False
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/batch",
            json={
                "simulation_id": "s",
                "interviews": [{"agent_id": 0, "prompt": "hi"}],
            },
        )
        assert resp.status_code == 400

    def test_happy_path_optimizes_each_prompt(
        self, client, builder_user, login_as, fake_runner
    ):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/batch",
            json={
                "simulation_id": "s",
                "interviews": [
                    {"agent_id": 0, "prompt": "q1"},
                    {"agent_id": 1, "prompt": "q2", "platform": "reddit"},
                ],
                "platform": "twitter",
                "timeout": 90,
            },
        )
        assert resp.status_code == 200
        call = [c for c in fake_runner["calls"] if c[0] == "batch"][-1]
        kw = call[1]
        assert kw["platform"] == "twitter"
        assert kw["timeout"] == 90
        # 모든 prompt 가 PREFIX 로 최적화됨
        for itv in kw["interviews"]:
            assert itv["prompt"].startswith(INTERVIEW_PROMPT_PREFIX)


# ============================================================================
# POST /interview/all
# ============================================================================

class TestInterviewAll:
    def test_missing_sim_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/interview/all", json={})
        assert resp.status_code == 400

    def test_missing_prompt_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/all",
            json={"simulation_id": "s"},
        )
        assert resp.status_code == 400

    def test_env_dead_400(self, client, builder_user, login_as, fake_runner):
        fake_runner["alive"] = False
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/all",
            json={"simulation_id": "s", "prompt": "hi"},
        )
        assert resp.status_code == 400

    def test_happy_path(self, client, builder_user, login_as, fake_runner):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/all",
            json={"simulation_id": "s", "prompt": "Q?", "platform": "reddit"},
        )
        assert resp.status_code == 200
        call = [c for c in fake_runner["calls"] if c[0] == "all"][-1]
        kw = call[1]
        assert kw["platform"] == "reddit"
        assert kw["prompt"].startswith(INTERVIEW_PROMPT_PREFIX)

    def test_timeout_returns_504(self, client, builder_user, login_as, monkeypatch):
        class _R:
            @staticmethod
            def check_env_alive(_):
                return True
            @staticmethod
            def interview_all_agents(**kw):
                raise TimeoutError("slow")

        monkeypatch.setattr(interview_routes, "SimulationRunner", _R)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/all",
            json={"simulation_id": "s", "prompt": "hi"},
        )
        assert resp.status_code == 504


# ============================================================================
# POST /interview/history
# ============================================================================

class TestInterviewHistory:
    def test_missing_sim_400(self, client, builder_user, login_as):
        login_as("builder@test.local")
        resp = client.post("/api/simulation/interview/history", json={})
        assert resp.status_code == 400

    def test_returns_history(self, client, builder_user, login_as, fake_runner):
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/history",
            json={
                "simulation_id": "s",
                "platform": "reddit",
                "agent_id": 0,
                "limit": 50,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["count"] == 2
        # 호출 인자 검증
        call = [c for c in fake_runner["calls"] if c[0] == "history"][-1]
        kw = call[1]
        assert kw == {
            "simulation_id": "s",
            "platform": "reddit",
            "agent_id": 0,
            "limit": 50,
        }

    def test_runner_exception_500(self, client, builder_user, login_as, monkeypatch):
        class _R:
            @staticmethod
            def get_interview_history(**kw):
                raise RuntimeError("db down")

        monkeypatch.setattr(interview_routes, "SimulationRunner", _R)
        login_as("builder@test.local")
        resp = client.post(
            "/api/simulation/interview/history", json={"simulation_id": "s"}
        )
        assert resp.status_code == 500
