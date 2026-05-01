"""
SimulationRunner 단위 테스트 (`app/services/simulation_runner.py`).

검증 단위 (subprocess 시작/모니터링은 제외 — 별도 통합 테스트 영역):
- AgentAction / RoundSummary / SimulationRunState (add_action, to_dict, to_detail_dict)
- 상태 저장/로드 (파일 + 메모리 캐시)
- _atomic_write_json
- _read_actions_from_file: JSONL 파싱, event_type 스킵, agent_id 필터
- get_all_actions / get_actions / get_timeline / get_agent_stats
- _check_all_platforms_completed
- cleanup_simulation_logs
- get_running_simulations
- check_env_alive / get_env_status_detail
- interview_agent / interview_agents_batch / interview_all_agents (IPC 모킹)
- close_simulation_env

격리: RUN_STATE_DIR 을 monkeypatch 로 tmp_path 리다이렉트 + _run_states/_processes 초기화.
"""

import json
import os
from types import SimpleNamespace

import pytest

from app.services import simulation_runner as sr_mod
from app.services.simulation_runner import (
    AgentAction,
    RoundSummary,
    RunnerStatus,
    SimulationRunner,
    SimulationRunState,
)


@pytest.fixture
def isolated_runner(tmp_path, monkeypatch):
    """RUN_STATE_DIR 을 tmp_path 로 리다이렉트 + 클래스 상태 초기화."""
    monkeypatch.setattr(SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    # 메모리 상태 초기화 (전역 dict)
    saved_states = dict(SimulationRunner._run_states)
    saved_procs = dict(SimulationRunner._processes)
    SimulationRunner._run_states.clear()
    SimulationRunner._processes.clear()
    yield tmp_path
    SimulationRunner._run_states.clear()
    SimulationRunner._run_states.update(saved_states)
    SimulationRunner._processes.clear()
    SimulationRunner._processes.update(saved_procs)


def _action(round_num=1, platform="reddit", agent_id=1, **kw):
    defaults = dict(
        timestamp=f"2026-05-01T00:0{round_num}:00",
        agent_name=f"agent_{agent_id}",
        action_type="CREATE_POST",
        action_args={"content": "x"},
        result=None,
        success=True,
    )
    defaults.update(kw)
    return AgentAction(
        round_num=round_num, platform=platform, agent_id=agent_id, **defaults
    )


# ============================================================================
# AgentAction / RoundSummary / SimulationRunState
# ============================================================================

class TestAgentAction:
    def test_to_dict(self):
        a = _action(round_num=2, platform="twitter", agent_id=5)
        d = a.to_dict()
        assert d["round_num"] == 2
        assert d["platform"] == "twitter"
        assert d["agent_id"] == 5
        assert d["action_args"] == {"content": "x"}


class TestRoundSummary:
    def test_to_dict_includes_actions_count(self):
        rs = RoundSummary(
            round_num=1,
            start_time="2026-05-01T00:00:00",
            actions=[_action(), _action()],
        )
        d = rs.to_dict()
        assert d["actions_count"] == 2
        assert len(d["actions"]) == 2


class TestSimulationRunStateAddAction:
    def test_increments_platform_count(self):
        s = SimulationRunState(simulation_id="s1")
        s.add_action(_action(platform="twitter"))
        s.add_action(_action(platform="reddit"))
        s.add_action(_action(platform="twitter"))
        assert s.twitter_actions_count == 2
        assert s.reddit_actions_count == 1

    def test_recent_actions_capped_at_max(self):
        s = SimulationRunState(simulation_id="s1", max_recent_actions=3)
        for i in range(5):
            s.add_action(_action(round_num=i))
        assert len(s.recent_actions) == 3
        # 최신이 맨 앞
        assert s.recent_actions[0].round_num == 4

    def test_to_dict_includes_progress_percent(self):
        s = SimulationRunState(
            simulation_id="s1", current_round=5, total_rounds=20,
        )
        d = s.to_dict()
        assert d["progress_percent"] == 25.0

    def test_to_detail_dict_has_recent_actions(self):
        s = SimulationRunState(simulation_id="s1")
        s.add_action(_action())
        d = s.to_detail_dict()
        assert "recent_actions" in d
        assert len(d["recent_actions"]) == 1


# ============================================================================
# _atomic_write_json + _save_run_state / _load_run_state
# ============================================================================

class TestAtomicWriteAndStateRoundtrip:
    def test_atomic_write_creates_file(self, tmp_path):
        target = tmp_path / "out.json"
        SimulationRunner._atomic_write_json(str(target), {"a": 1})
        assert json.loads(target.read_text()) == {"a": 1}

    def test_save_load_roundtrip(self, isolated_runner):
        s = SimulationRunState(
            simulation_id="sim_x",
            runner_status=RunnerStatus.RUNNING,
            current_round=3,
            total_rounds=10,
            twitter_actions_count=5,
        )
        s.add_action(_action(round_num=3, platform="twitter"))
        SimulationRunner._save_run_state(s)
        # 캐시 클리어 후 디스크에서 로드
        SimulationRunner._run_states.clear()
        loaded = SimulationRunner._load_run_state("sim_x")
        assert loaded is not None
        assert loaded.runner_status == RunnerStatus.RUNNING
        assert loaded.current_round == 3
        assert len(loaded.recent_actions) == 1

    def test_load_missing_returns_none(self, isolated_runner):
        assert SimulationRunner._load_run_state("ghost") is None

    def test_load_corrupt_returns_none(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_bad"
        sim_dir.mkdir()
        (sim_dir / "run_state.json").write_text("{not-json")
        assert SimulationRunner._load_run_state("sim_bad") is None


# ============================================================================
# get_run_state
# ============================================================================

class TestGetRunState:
    def test_cache_hit(self, isolated_runner):
        s = SimulationRunState(simulation_id="sim_a")
        SimulationRunner._run_states["sim_a"] = s
        assert SimulationRunner.get_run_state("sim_a") is s

    def test_loads_from_disk_when_not_cached(self, isolated_runner):
        s = SimulationRunState(simulation_id="sim_b", current_round=7)
        SimulationRunner._save_run_state(s)
        SimulationRunner._run_states.clear()
        loaded = SimulationRunner.get_run_state("sim_b")
        assert loaded is not None
        assert loaded.current_round == 7

    def test_missing_returns_none(self, isolated_runner):
        assert SimulationRunner.get_run_state("ghost") is None


# ============================================================================
# _read_actions_from_file
# ============================================================================

class TestReadActionsFromFile:
    def _write(self, path, lines):
        with open(path, "w", encoding="utf-8") as f:
            for l in lines:
                f.write(json.dumps(l) + "\n")

    def test_returns_empty_when_file_missing(self, tmp_path):
        result = SimulationRunner._read_actions_from_file(str(tmp_path / "missing.jsonl"))
        assert result == []

    def test_skips_event_type_records(self, tmp_path):
        path = tmp_path / "actions.jsonl"
        self._write(path, [
            {"event_type": "simulation_start"},
            {"agent_id": 1, "action_type": "CREATE_POST", "round": 1, "timestamp": "t1"},
            {"event_type": "round_end"},
        ])
        result = SimulationRunner._read_actions_from_file(
            str(path), default_platform="reddit"
        )
        assert len(result) == 1
        assert result[0].agent_id == 1
        assert result[0].platform == "reddit"

    def test_filters_by_platform(self, tmp_path):
        path = tmp_path / "actions.jsonl"
        self._write(path, [
            {"agent_id": 1, "action_type": "X", "platform": "twitter", "round": 1},
            {"agent_id": 2, "action_type": "Y", "platform": "reddit", "round": 1},
        ])
        result = SimulationRunner._read_actions_from_file(
            str(path), platform_filter="twitter"
        )
        assert len(result) == 1
        assert result[0].platform == "twitter"

    def test_filters_by_agent_id_and_round(self, tmp_path):
        path = tmp_path / "actions.jsonl"
        self._write(path, [
            {"agent_id": 1, "action_type": "X", "round": 1},
            {"agent_id": 2, "action_type": "X", "round": 1},
            {"agent_id": 1, "action_type": "X", "round": 2},
        ])
        result = SimulationRunner._read_actions_from_file(
            str(path), default_platform="r", agent_id=1, round_num=2,
        )
        assert len(result) == 1
        assert result[0].agent_id == 1
        assert result[0].round_num == 2

    def test_skips_records_without_agent_id(self, tmp_path):
        path = tmp_path / "actions.jsonl"
        self._write(path, [
            {"action_type": "X", "round": 1},  # agent_id 없음
            {"agent_id": 1, "action_type": "Y", "round": 1},
        ])
        result = SimulationRunner._read_actions_from_file(str(path))
        assert len(result) == 1
        assert result[0].agent_id == 1

    def test_skips_invalid_json_lines(self, tmp_path):
        path = tmp_path / "actions.jsonl"
        with open(path, "w") as f:
            f.write('{"agent_id": 1, "action_type": "X", "round": 1}\n')
            f.write("not json\n")
            f.write('{"agent_id": 2, "action_type": "Y", "round": 1}\n')
        result = SimulationRunner._read_actions_from_file(
            str(path), default_platform="r"
        )
        assert len(result) == 2


# ============================================================================
# get_all_actions / get_actions / get_timeline / get_agent_stats
# ============================================================================

class TestActionAggregations:
    def _setup_actions(self, sim_dir, twitter=None, reddit=None, fallback=None):
        sim_dir = sim_dir
        sim_dir.mkdir(exist_ok=True, parents=True)
        if twitter is not None:
            t_dir = sim_dir / "twitter"
            t_dir.mkdir()
            with open(t_dir / "actions.jsonl", "w") as f:
                for r in twitter:
                    f.write(json.dumps(r) + "\n")
        if reddit is not None:
            r_dir = sim_dir / "reddit"
            r_dir.mkdir()
            with open(r_dir / "actions.jsonl", "w") as f:
                for r in reddit:
                    f.write(json.dumps(r) + "\n")
        if fallback is not None:
            with open(sim_dir / "actions.jsonl", "w") as f:
                for r in fallback:
                    f.write(json.dumps(r) + "\n")

    def test_get_all_actions_merges_platforms(self, isolated_runner, tmp_path):
        self._setup_actions(
            tmp_path / "sim_x",
            twitter=[
                {"agent_id": 1, "action_type": "POST", "round": 1, "timestamp": "2026-05-01T01:00"}
            ],
            reddit=[
                {"agent_id": 2, "action_type": "POST", "round": 1, "timestamp": "2026-05-01T02:00"}
            ],
        )
        result = SimulationRunner.get_all_actions("sim_x")
        assert len(result) == 2
        # 시간 내림차순 정렬 — 02:00 가 먼저
        assert result[0].timestamp == "2026-05-01T02:00"

    def test_get_all_actions_filters_platform(self, isolated_runner, tmp_path):
        self._setup_actions(
            tmp_path / "sim_x",
            twitter=[{"agent_id": 1, "action_type": "POST", "round": 1, "timestamp": "t1"}],
            reddit=[{"agent_id": 2, "action_type": "POST", "round": 1, "timestamp": "t2"}],
        )
        result = SimulationRunner.get_all_actions("sim_x", platform="twitter")
        assert len(result) == 1
        assert result[0].agent_id == 1

    def test_get_all_actions_falls_back_to_single_file(
        self, isolated_runner, tmp_path
    ):
        self._setup_actions(
            tmp_path / "sim_y",
            fallback=[
                {"agent_id": 1, "action_type": "X", "round": 1,
                 "platform": "reddit", "timestamp": "t1"}
            ],
        )
        result = SimulationRunner.get_all_actions("sim_y")
        assert len(result) == 1

    def test_get_actions_pagination(self, isolated_runner, tmp_path):
        self._setup_actions(
            tmp_path / "sim_z",
            reddit=[
                {"agent_id": i, "action_type": "X", "round": 1,
                 "timestamp": f"2026-05-01T0{i}:00"}
                for i in range(5)
            ],
        )
        page1 = SimulationRunner.get_actions("sim_z", limit=2, offset=0)
        page2 = SimulationRunner.get_actions("sim_z", limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2

    def test_get_timeline_groups_by_round(self, isolated_runner, tmp_path):
        self._setup_actions(
            tmp_path / "sim_t",
            twitter=[
                {"agent_id": 1, "action_type": "POST", "round": 1, "timestamp": "t1"},
                {"agent_id": 2, "action_type": "LIKE", "round": 1, "timestamp": "t2"},
                {"agent_id": 1, "action_type": "POST", "round": 2, "timestamp": "t3"},
            ],
        )
        timeline = SimulationRunner.get_timeline("sim_t")
        assert len(timeline) == 2
        round1 = next(r for r in timeline if r["round_num"] == 1)
        assert round1["twitter_actions"] == 2
        assert round1["active_agents_count"] == 2
        assert round1["action_types"]["POST"] == 1
        assert round1["action_types"]["LIKE"] == 1

    def test_get_timeline_filters_round_range(self, isolated_runner, tmp_path):
        self._setup_actions(
            tmp_path / "sim_r",
            twitter=[
                {"agent_id": 1, "action_type": "POST", "round": i, "timestamp": f"t{i}"}
                for i in range(5)
            ],
        )
        timeline = SimulationRunner.get_timeline("sim_r", start_round=2, end_round=3)
        assert {r["round_num"] for r in timeline} == {2, 3}

    def test_get_agent_stats_aggregates(self, isolated_runner, tmp_path):
        self._setup_actions(
            tmp_path / "sim_s",
            twitter=[
                {"agent_id": 1, "agent_name": "Alice", "action_type": "POST",
                 "round": 1, "timestamp": "t1"},
                {"agent_id": 1, "agent_name": "Alice", "action_type": "POST",
                 "round": 2, "timestamp": "t2"},
                {"agent_id": 2, "agent_name": "Bob", "action_type": "LIKE",
                 "round": 1, "timestamp": "t3"},
            ],
        )
        stats = SimulationRunner.get_agent_stats("sim_s")
        assert len(stats) == 2
        # 정렬: total_actions 내림차순
        assert stats[0]["agent_id"] == 1
        assert stats[0]["total_actions"] == 2
        assert stats[0]["twitter_actions"] == 2


# ============================================================================
# _check_all_platforms_completed
# ============================================================================

class TestCheckAllPlatformsCompleted:
    def test_no_logs_returns_false(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_a"
        sim_dir.mkdir()
        state = SimulationRunState(simulation_id="sim_a")
        # 프로세스 미등록 + 파일 없음 → 활성화된 플랫폼 없음 → False
        assert (
            SimulationRunner._check_all_platforms_completed(state) is False
        )

    def test_all_completed(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_b"
        (sim_dir / "twitter").mkdir(parents=True)
        (sim_dir / "reddit").mkdir(parents=True)
        (sim_dir / "twitter" / "actions.jsonl").write_text("")
        (sim_dir / "reddit" / "actions.jsonl").write_text("")
        state = SimulationRunState(
            simulation_id="sim_b",
            twitter_completed=True, reddit_completed=True,
        )
        assert SimulationRunner._check_all_platforms_completed(state) is True

    def test_one_pending_returns_false(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_c"
        (sim_dir / "twitter").mkdir(parents=True)
        (sim_dir / "reddit").mkdir(parents=True)
        (sim_dir / "twitter" / "actions.jsonl").write_text("")
        (sim_dir / "reddit" / "actions.jsonl").write_text("")
        state = SimulationRunState(
            simulation_id="sim_c",
            twitter_completed=True, reddit_completed=False,
        )
        assert SimulationRunner._check_all_platforms_completed(state) is False

    def test_process_exited_overrides_pending_files(
        self, isolated_runner, tmp_path
    ):
        sim_dir = tmp_path / "sim_d"
        sim_dir.mkdir()
        # 프로세스 등록 (이미 종료)
        SimulationRunner._processes["sim_d"] = SimpleNamespace(
            poll=lambda: 0  # 종료된 상태
        )
        state = SimulationRunState(simulation_id="sim_d")
        assert SimulationRunner._check_all_platforms_completed(state) is True


# ============================================================================
# cleanup_simulation_logs
# ============================================================================

class TestCleanupSimulationLogs:
    def test_no_directory(self, isolated_runner):
        result = SimulationRunner.cleanup_simulation_logs("ghost")
        assert result["success"] is True
        assert "필요 없습니다" in result["message"]

    def test_removes_files_and_action_logs(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_x"
        (sim_dir / "twitter").mkdir(parents=True)
        (sim_dir / "reddit").mkdir(parents=True)

        # 정리 대상 파일 생성
        for fname in ["run_state.json", "stdout.log", "stderr.log",
                      "twitter_simulation.db", "reddit_simulation.db",
                      "env_status.json", "simulation.log"]:
            (sim_dir / fname).write_text("data")
        (sim_dir / "twitter" / "actions.jsonl").write_text("[]")
        (sim_dir / "reddit" / "actions.jsonl").write_text("[]")
        # 보존 대상: simulation_config.json
        (sim_dir / "simulation_config.json").write_text("{}")

        # 메모리 캐시에 등록 → 정리 후 제거 확인
        SimulationRunner._run_states["sim_x"] = SimulationRunState(simulation_id="sim_x")

        result = SimulationRunner.cleanup_simulation_logs("sim_x")
        assert result["success"] is True
        assert "run_state.json" in result["cleaned_files"]
        assert "twitter/actions.jsonl" in result["cleaned_files"]
        assert not (sim_dir / "run_state.json").exists()
        assert not (sim_dir / "twitter" / "actions.jsonl").exists()
        # 보존 대상은 살아있음
        assert (sim_dir / "simulation_config.json").exists()
        # 캐시에서 제거
        assert "sim_x" not in SimulationRunner._run_states


# ============================================================================
# get_running_simulations
# ============================================================================

class TestGetRunningSimulations:
    def test_filters_by_poll(self, isolated_runner):
        SimulationRunner._processes["sim_a"] = SimpleNamespace(poll=lambda: None)  # 실행 중
        SimulationRunner._processes["sim_b"] = SimpleNamespace(poll=lambda: 0)  # 종료
        SimulationRunner._processes["sim_c"] = SimpleNamespace(poll=lambda: None)  # 실행 중
        running = SimulationRunner.get_running_simulations()
        assert set(running) == {"sim_a", "sim_c"}


# ============================================================================
# check_env_alive / get_env_status_detail
# ============================================================================

class TestCheckEnvAlive:
    def test_no_directory(self, isolated_runner):
        assert SimulationRunner.check_env_alive("missing") is False

    def test_delegates_to_ipc(self, isolated_runner, tmp_path, monkeypatch):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()

        class _FakeIPC:
            def __init__(self, _):
                pass
            def check_env_alive(self):
                return True

        monkeypatch.setattr(sr_mod, "make_ipc_client",_FakeIPC)
        assert SimulationRunner.check_env_alive("sim_x") is True


class TestGetEnvStatusDetail:
    def test_missing_returns_default(self, isolated_runner):
        result = SimulationRunner.get_env_status_detail("ghost")
        assert result["status"] == "stopped"
        assert result["twitter_available"] is False

    def test_returns_status(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        (sim_dir / "env_status.json").write_text(json.dumps({
            "status": "alive",
            "twitter_available": True,
            "reddit_available": False,
            "timestamp": "2026-05-01",
        }))
        result = SimulationRunner.get_env_status_detail("sim_x")
        assert result["status"] == "alive"
        assert result["twitter_available"] is True

    def test_corrupt_returns_default(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_y"
        sim_dir.mkdir()
        (sim_dir / "env_status.json").write_text("{not-json")
        result = SimulationRunner.get_env_status_detail("sim_y")
        assert result["status"] == "stopped"


# ============================================================================
# interview_agent
# ============================================================================

class _IPCResponse:
    def __init__(self, status="completed", result=None, error=None, ts="2026-05-01"):
        self.status = SimpleNamespace(value=status)
        self.result = result
        self.error = error
        self.timestamp = ts


class _IPCClientFactory:
    """모듈 레벨 make_ipc_client 모킹 헬퍼."""
    def __init__(self, alive=True, response=None):
        self.alive = alive
        self.response = response or _IPCResponse(result={"text": "ok"})
        self.calls = []

    def __call__(self, sim_dir):
        return self  # 자기 자신을 client 로 반환

    def check_env_alive(self):
        return self.alive

    def send_interview(self, **kw):
        self.calls.append(("interview", kw))
        return self.response

    def send_batch_interview(self, **kw):
        self.calls.append(("batch", kw))
        return self.response

    def send_close_env(self, **kw):
        self.calls.append(("close", kw))
        return self.response


class TestInterviewAgent:
    def test_missing_dir_raises(self, isolated_runner):
        with pytest.raises(ValueError, match="존재하지 않습니다"):
            SimulationRunner.interview_agent("ghost", agent_id=1, prompt="?")

    def test_env_not_alive_raises(self, isolated_runner, tmp_path, monkeypatch):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        ipc = _IPCClientFactory(alive=False)
        monkeypatch.setattr(sr_mod, "make_ipc_client",ipc)
        with pytest.raises(ValueError, match="실행 중이 아니"):
            SimulationRunner.interview_agent("sim_x", agent_id=1, prompt="?")

    def test_completed_response(self, isolated_runner, tmp_path, monkeypatch):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        ipc = _IPCClientFactory(response=_IPCResponse(result={"answer": "yes"}))
        monkeypatch.setattr(sr_mod, "make_ipc_client",ipc)
        result = SimulationRunner.interview_agent(
            "sim_x", agent_id=42, prompt="hello", platform="reddit",
        )
        assert result["success"] is True
        assert result["agent_id"] == 42
        assert result["result"] == {"answer": "yes"}
        assert ipc.calls[0][1]["platform"] == "reddit"

    def test_failed_response(self, isolated_runner, tmp_path, monkeypatch):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        ipc = _IPCClientFactory(
            response=_IPCResponse(status="failed", error="agent not found")
        )
        monkeypatch.setattr(sr_mod, "make_ipc_client",ipc)
        result = SimulationRunner.interview_agent(
            "sim_x", agent_id=99, prompt="?",
        )
        assert result["success"] is False
        assert result["error"] == "agent not found"


class TestInterviewAgentsBatch:
    def test_batch_completed(self, isolated_runner, tmp_path, monkeypatch):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        ipc = _IPCClientFactory(response=_IPCResponse(result={"all": "good"}))
        monkeypatch.setattr(sr_mod, "make_ipc_client",ipc)
        result = SimulationRunner.interview_agents_batch(
            "sim_x",
            interviews=[{"agent_id": 1, "prompt": "q"}, {"agent_id": 2, "prompt": "q"}],
        )
        assert result["success"] is True
        assert result["interviews_count"] == 2


class TestInterviewAllAgents:
    def test_missing_config(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        with pytest.raises(ValueError, match="설정이 존재하지"):
            SimulationRunner.interview_all_agents("sim_x", prompt="q")

    def test_no_agent_configs(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        (sim_dir / "simulation_config.json").write_text(
            json.dumps({"agent_configs": []})
        )
        with pytest.raises(ValueError, match="Agent가 없습니다"):
            SimulationRunner.interview_all_agents("sim_x", prompt="q")

    def test_delegates_to_batch(self, isolated_runner, tmp_path, monkeypatch):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        (sim_dir / "simulation_config.json").write_text(
            json.dumps({"agent_configs": [
                {"agent_id": 1}, {"agent_id": 2}, {"agent_id": 3}
            ]})
        )
        ipc = _IPCClientFactory()
        monkeypatch.setattr(sr_mod, "make_ipc_client",ipc)
        result = SimulationRunner.interview_all_agents("sim_x", prompt="q")
        # batch 가 호출됐고 3개 interview 전달됨
        assert ipc.calls[0][0] == "batch"
        assert len(ipc.calls[0][1]["interviews"]) == 3


# ============================================================================
# close_simulation_env
# ============================================================================

class TestCloseSimulationEnv:
    def test_missing_raises(self, isolated_runner):
        with pytest.raises(ValueError, match="존재하지 않습니다"):
            SimulationRunner.close_simulation_env("ghost")

    def test_already_stopped(self, isolated_runner, tmp_path, monkeypatch):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        ipc = _IPCClientFactory(alive=False)
        monkeypatch.setattr(sr_mod, "make_ipc_client",ipc)
        result = SimulationRunner.close_simulation_env("sim_x")
        assert result["success"] is True
        assert "이미 종료" in result["message"]

    def test_send_close_command(self, isolated_runner, tmp_path, monkeypatch):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        ipc = _IPCClientFactory(response=_IPCResponse(result={"closed": True}))
        monkeypatch.setattr(sr_mod, "make_ipc_client",ipc)
        result = SimulationRunner.close_simulation_env("sim_x", timeout=5.0)
        assert result["success"] is True
        assert result["result"] == {"closed": True}
        assert ipc.calls[0][0] == "close"

    def test_timeout_treated_as_success(self, isolated_runner, tmp_path, monkeypatch):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()

        class _IPCTimeout:
            def __init__(self, _):
                pass
            def check_env_alive(self):
                return True
            def send_close_env(self, **kw):
                raise TimeoutError("...")

        monkeypatch.setattr(sr_mod, "make_ipc_client",_IPCTimeout)
        result = SimulationRunner.close_simulation_env("sim_x")
        assert result["success"] is True
        assert "타임아웃" in result["message"]


# ============================================================================
# get_interview_history (sqlite)
# ============================================================================

class TestGetInterviewHistory:
    def _make_db(self, db_path, rows):
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE trace (user_id INTEGER, info TEXT, action TEXT, "
            "created_at TEXT)"
        )
        for r in rows:
            conn.execute(
                "INSERT INTO trace (user_id, info, action, created_at) "
                "VALUES (?, ?, ?, ?)",
                (r["user_id"], r["info"], r.get("action", "interview"), r["created_at"])
            )
        conn.commit()
        conn.close()

    def test_empty_when_db_missing(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        result = SimulationRunner.get_interview_history("sim_x")
        assert result == []

    def test_reads_from_reddit_db(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_x"
        sim_dir.mkdir()
        self._make_db(sim_dir / "reddit_simulation.db", [
            {"user_id": 1, "info": json.dumps({"prompt": "q1", "response": "a1"}),
             "created_at": "2026-05-01T01:00"},
            {"user_id": 2, "info": json.dumps({"prompt": "q2", "response": "a2"}),
             "created_at": "2026-05-01T02:00"},
        ])
        result = SimulationRunner.get_interview_history("sim_x", platform="reddit")
        assert len(result) == 2
        # 시간 내림차순
        assert result[0]["timestamp"] == "2026-05-01T02:00"
        assert result[0]["platform"] == "reddit"

    def test_filter_by_agent_id(self, isolated_runner, tmp_path):
        sim_dir = tmp_path / "sim_y"
        sim_dir.mkdir()
        self._make_db(sim_dir / "reddit_simulation.db", [
            {"user_id": 1, "info": json.dumps({}), "created_at": "t1"},
            {"user_id": 2, "info": json.dumps({}), "created_at": "t2"},
        ])
        result = SimulationRunner.get_interview_history(
            "sim_y", platform="reddit", agent_id=2
        )
        assert len(result) == 1
        assert result[0]["agent_id"] == 2
