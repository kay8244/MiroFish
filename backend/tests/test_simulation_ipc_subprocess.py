"""
서브프로세스 측 IPC 통합 e2e 테스트 (TODOS #2 잔여).

검증 시나리오 (백엔드 무관):
- `make_ipc_server()` 가 반환한 서버 객체로 Flask 측 클라이언트와 라운드트립.
- 서브프로세스 스크립트가 호출하는 새 API: `update_status(status, twitter_available, reddit_available)`,
  `poll_commands()`, `send_success()`, `send_error()`, `start()`, `stop()`.
- Flask 측: `make_ipc_client()` 가 반환한 클라이언트의 `get_env_status()` 가
  서버가 쓴 platform_available 필드까지 보여줌.

파일 IPC: 임시 디렉토리, REDIS_URL 미설정.
Redis IPC: fakeredis 로 인-메모리 시뮬레이션.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict

import fakeredis
import pytest

from app.services import simulation_ipc_factory
from app.services.simulation_ipc import (
    CommandStatus,
    CommandType,
    IPCResponse,
    SimulationIPCClient,
    SimulationIPCServer,
)
from app.services.simulation_ipc_redis import (
    RedisSimulationIPCClient,
    RedisSimulationIPCServer,
)


# ---------------------------------------------------------------------------
# 헬퍼: 서브프로세스 측 process_commands 루프 모방
# ---------------------------------------------------------------------------

def _drain_one_command(server, env: Dict[str, Any]) -> bool:
    """
    서브프로세스 스크립트의 process_commands() 와 동일한 분기 흐름.
    실제 oasis env.step 대신 `env` dict 에 의존하는 단순 모의를 사용.
    Returns: True 계속, False 종료.
    """
    cmd = server.poll_commands()
    if cmd is None:
        return True

    if cmd.command_type == CommandType.INTERVIEW:
        agent_id = cmd.args.get("agent_id", 0)
        prompt = cmd.args.get("prompt", "")
        server.send_success(cmd.command_id, {
            "agent_id": agent_id,
            "response": f"echo:{prompt}",
            "platform": cmd.args.get("platform"),
        })
        return True

    if cmd.command_type == CommandType.BATCH_INTERVIEW:
        results = {
            iv["agent_id"]: {
                "agent_id": iv["agent_id"],
                "response": f"echo:{iv['prompt']}",
            }
            for iv in cmd.args.get("interviews", [])
        }
        server.send_success(cmd.command_id, {
            "interviews_count": len(results),
            "results": results,
        })
        return True

    if cmd.command_type == CommandType.CLOSE_ENV:
        server.send_success(cmd.command_id, {"message": "closing"})
        return False

    server.send_error(cmd.command_id, f"unknown: {cmd.command_type}")
    return True


def _run_server_loop(server, stop_evt: threading.Event):
    """서브프로세스 측 폴링 루프를 모방하는 백그라운드 스레드 (1개씩 처리)."""
    server.start()
    try:
        while not stop_evt.is_set():
            cont = _drain_one_command(server, env={})
            if not cont:
                break
            time.sleep(0.02)
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_factory_log():
    simulation_ipc_factory._logged_backend = False
    yield
    simulation_ipc_factory._logged_backend = False


@pytest.fixture
def file_sim_dir(tmp_path, monkeypatch):
    """파일 IPC 시나리오: REDIS_URL 미설정."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    sim_dir = tmp_path / "sim_file"
    sim_dir.mkdir()
    return str(sim_dir)


@pytest.fixture
def redis_sim_setup(tmp_path, monkeypatch):
    """Redis IPC 시나리오: fakeredis 인-메모리 + REDIS_URL 설정."""
    monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
    sim_dir = tmp_path / "sim_redis"
    sim_dir.mkdir()
    fake = fakeredis.FakeRedis(decode_responses=True)
    # 두 객체가 같은 fake 클라이언트를 공유하도록 강제 주입
    return str(sim_dir), fake


# ---------------------------------------------------------------------------
# 1. 새 update_status API — 양 백엔드 platform_available 필드
# ---------------------------------------------------------------------------

class TestUpdateStatusWithPlatforms:
    def test_file_server_writes_platform_fields(self, file_sim_dir):
        server = simulation_ipc_factory.make_ipc_server(file_sim_dir)
        assert isinstance(server, SimulationIPCServer)
        server.update_status("alive", twitter_available=True, reddit_available=False)

        client = simulation_ipc_factory.make_ipc_client(file_sim_dir)
        status = client.get_env_status()
        assert status["status"] == "alive"
        assert status["twitter_available"] is True
        assert status["reddit_available"] is False

    def test_redis_server_writes_platform_fields(self, redis_sim_setup):
        sim_dir, fake = redis_sim_setup
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake)
        server.update_status("alive", twitter_available=False, reddit_available=True)

        client = RedisSimulationIPCClient(sim_dir, redis_client=fake)
        status = client.get_env_status()
        assert status["status"] == "alive"
        assert status["twitter_available"] is False
        assert status["reddit_available"] is True

    def test_factory_returns_redis_server_when_redis_url_set(self, redis_sim_setup):
        sim_dir, _fake = redis_sim_setup
        server = simulation_ipc_factory.make_ipc_server(sim_dir)
        assert isinstance(server, RedisSimulationIPCServer)


# ---------------------------------------------------------------------------
# 2. e2e 라운드트립 — Flask 측 client → 서브프로세스 측 server (양 백엔드)
# ---------------------------------------------------------------------------

class TestSubprocessRoundtrip:
    """서브프로세스 스크립트가 새 API 로 명령을 처리하는지 e2e 검증."""

    def _run_interview(self, client, server) -> IPCResponse:
        """서버를 백그라운드 루프로 띄우고, 클라이언트로 1건 전송."""
        stop = threading.Event()
        t = threading.Thread(target=_run_server_loop, args=(server, stop), daemon=True)
        t.start()
        try:
            resp = client.send_interview(agent_id=42, prompt="hello", timeout=5.0)
        finally:
            stop.set()
            t.join(timeout=2.0)
        return resp

    def test_file_backend_interview_roundtrip(self, file_sim_dir):
        client = simulation_ipc_factory.make_ipc_client(file_sim_dir)
        server = simulation_ipc_factory.make_ipc_server(file_sim_dir)
        resp = self._run_interview(client, server)
        assert resp.status == CommandStatus.COMPLETED
        assert resp.result["agent_id"] == 42
        assert resp.result["response"] == "echo:hello"

    def test_redis_backend_interview_roundtrip(self, redis_sim_setup):
        sim_dir, fake = redis_sim_setup
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake)
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake)
        resp = self._run_interview(client, server)
        assert resp.status == CommandStatus.COMPLETED
        assert resp.result["agent_id"] == 42
        assert resp.result["response"] == "echo:hello"

    def test_file_backend_batch_interview_roundtrip(self, file_sim_dir):
        client = simulation_ipc_factory.make_ipc_client(file_sim_dir)
        server = simulation_ipc_factory.make_ipc_server(file_sim_dir)

        stop = threading.Event()
        t = threading.Thread(target=_run_server_loop, args=(server, stop), daemon=True)
        t.start()
        try:
            resp = client.send_batch_interview(
                interviews=[
                    {"agent_id": 1, "prompt": "Q1"},
                    {"agent_id": 2, "prompt": "Q2"},
                ],
                timeout=5.0,
            )
        finally:
            stop.set()
            t.join(timeout=2.0)

        assert resp.status == CommandStatus.COMPLETED
        assert resp.result["interviews_count"] == 2
        # JSON 라운드트립으로 dict 키가 문자열화될 수 있어 양쪽 형식 모두 허용
        results = resp.result["results"]
        assert {str(k) for k in results.keys()} == {"1", "2"}

    def test_redis_backend_close_env_terminates_server(self, redis_sim_setup):
        sim_dir, fake = redis_sim_setup
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake)
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake)

        stop = threading.Event()
        t = threading.Thread(target=_run_server_loop, args=(server, stop), daemon=True)
        t.start()
        try:
            resp = client.send_close_env(timeout=5.0)
        finally:
            stop.set()
            t.join(timeout=2.0)

        assert resp.status == CommandStatus.COMPLETED
        # 서버 stop() 이 호출되어 status hash 가 stopped 로 갱신됨
        assert client.get_env_status()["status"] == "stopped"


# ---------------------------------------------------------------------------
# 3. start/stop → status 흐름 (서브프로세스가 거치는 라이프사이클)
# ---------------------------------------------------------------------------

class TestLifecycleStatus:
    def test_file_lifecycle(self, file_sim_dir):
        server = simulation_ipc_factory.make_ipc_server(file_sim_dir)
        client = simulation_ipc_factory.make_ipc_client(file_sim_dir)

        # 시뮬레이션 진행 중: "running" — Flask 가 alive 로 잘못 판단하면 안 됨
        server.update_status("running")
        assert client.check_env_alive() is False
        assert client.get_env_status()["status"] == "running"

        # 시뮬레이션 종료 후 명령 대기: alive
        server.start()
        assert client.check_env_alive() is True

        # 명령 처리 종료
        server.stop()
        assert client.check_env_alive() is False
        assert client.get_env_status()["status"] == "stopped"

    def test_redis_lifecycle(self, redis_sim_setup):
        sim_dir, fake = redis_sim_setup
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake)
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake)

        server.update_status("running")
        assert client.check_env_alive() is False

        server.start()
        assert client.check_env_alive() is True

        server.stop()
        assert client.check_env_alive() is False
