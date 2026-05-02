"""
실제 Redis 통합 테스트 — cross-process 라운드트립 검증 (TODOS #2 통합 검증).

fakeredis 가 아닌 실제 redis-server 와 별도 Python 서브프로세스를 띄워서
production 경로를 검증.

전제: 로컬 redis-server 가 :6379 에서 동작 중이거나 REDIS_TEST_URL 로 지정.
미동작 시 자동 skip (CI 안정성).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
import uuid

import pytest

# 프로젝트 루트에서 import 가능하도록 sys.path 조정 (테스트 환경 보호)
from app.services.simulation_ipc import CommandStatus
from app.services.simulation_ipc_factory import make_ipc_client


REDIS_TEST_URL = os.environ.get("REDIS_TEST_URL", "redis://localhost:6379/15")


def _redis_available() -> bool:
    try:
        import redis
        client = redis.from_url(REDIS_TEST_URL, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason=f"redis 서버 미동작 ({REDIS_TEST_URL})",
)


@pytest.fixture
def sim_dir(tmp_path):
    """고유 sim_id 디렉토리 (다른 테스트 잔여 키와 격리)."""
    d = tmp_path / f"sim_integration_{uuid.uuid4().hex[:8]}"
    d.mkdir()
    return str(d)


@pytest.fixture
def redis_env(monkeypatch):
    """REDIS_URL 을 테스트 DB 로 설정. 자동 cleanup."""
    monkeypatch.setenv("REDIS_URL", REDIS_TEST_URL)
    yield REDIS_TEST_URL
    # 테스트 DB 비우기
    import redis
    client = redis.from_url(REDIS_TEST_URL)
    client.flushdb()


def _run_subprocess_server(sim_dir: str, redis_url: str, max_commands: int = 1) -> subprocess.Popen:
    """
    별도 Python 프로세스에서 IPC 서버 폴링 루프를 띄움.
    `max_commands` 개 처리하면 종료 (테스트 격리).
    """
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = textwrap.dedent(f"""
        import sys, os, time
        sys.path.insert(0, {backend_dir!r})
        os.environ['REDIS_URL'] = {redis_url!r}

        from app.services.simulation_ipc_factory import make_ipc_server
        from app.services.simulation_ipc import CommandType

        server = make_ipc_server({sim_dir!r})
        server.start()

        processed = 0
        max_commands = {max_commands}
        deadline = time.time() + 15.0

        try:
            while processed < max_commands and time.time() < deadline:
                cmd = server.poll_commands()
                if cmd is None:
                    time.sleep(0.05)
                    continue

                if cmd.command_type == CommandType.INTERVIEW:
                    server.send_success(cmd.command_id, {{
                        "agent_id": cmd.args.get("agent_id"),
                        "response": "subprocess_echo:" + cmd.args.get("prompt", ""),
                    }})
                elif cmd.command_type == CommandType.CLOSE_ENV:
                    server.send_success(cmd.command_id, {{"message": "closing"}})
                else:
                    server.send_error(cmd.command_id, "unsupported in test")
                processed += 1
        finally:
            server.stop()
    """)
    return subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class TestRealRedisRoundtrip:
    def test_subprocess_server_handles_interview(self, sim_dir, redis_env):
        """실제 redis 를 통한 cross-process interview 라운드트립."""
        proc = _run_subprocess_server(sim_dir, redis_env, max_commands=1)
        try:
            # 서버 start 가 status hash 에 alive 를 쓸 때까지 잠깐 대기
            client = make_ipc_client(sim_dir)
            for _ in range(50):
                if client.check_env_alive():
                    break
                time.sleep(0.05)
            assert client.check_env_alive() is True

            resp = client.send_interview(agent_id=7, prompt="ping", timeout=10.0)
            assert resp.status == CommandStatus.COMPLETED
            assert resp.result["agent_id"] == 7
            assert resp.result["response"] == "subprocess_echo:ping"
        finally:
            proc.wait(timeout=10)

        # 서브프로세스 정상 종료 + stop() 호출되어 status 가 stopped 로
        assert proc.returncode == 0, (
            f"stderr: {proc.stderr.read().decode(errors='replace')}"
        )

    def test_subprocess_server_handles_close_env(self, sim_dir, redis_env):
        """close_env 명령으로 응답 받은 뒤 서브프로세스 정상 종료."""
        proc = _run_subprocess_server(sim_dir, redis_env, max_commands=1)
        try:
            client = make_ipc_client(sim_dir)
            for _ in range(50):
                if client.check_env_alive():
                    break
                time.sleep(0.05)

            resp = client.send_close_env(timeout=10.0)
            assert resp.status == CommandStatus.COMPLETED
            assert resp.result["message"] == "closing"
        finally:
            proc.wait(timeout=10)

        assert proc.returncode == 0
        # stop() 후 status 가 stopped
        client = make_ipc_client(sim_dir)
        assert client.check_env_alive() is False
        assert client.get_env_status()["status"] == "stopped"
