"""
Redis IPC 단위 테스트 (`app/services/simulation_ipc_redis.py`).

`fakeredis` 로 실제 Redis 없이 단위 테스트. 검증 단위:
- 키 헬퍼: sim_id 추출 + key 빌더
- get_redis_client: REDIS_URL env 우선
- RedisSimulationIPCClient: send_command (happy / timeout) + 래퍼들 + check_env_alive
- RedisSimulationIPCServer: start/stop status hash, poll_commands FIFO + atomic LPOP,
  send_response (LPUSH + EXPIRE TTL), 손상 메시지 처리

`test_simulation_ipc.py` (file IPC) 와 동일한 행동 계약을 보장하는 페어 테스트.
"""

from __future__ import annotations

import json
import os
import threading
import time

import fakeredis
import pytest

from app.services.simulation_ipc import (
    CommandStatus,
    CommandType,
    IPCCommand,
    IPCResponse,
)
from app.services.simulation_ipc_redis import (
    RedisSimulationIPCClient,
    RedisSimulationIPCServer,
    _cmd_queue_key,
    _resp_key,
    _sim_id_from_dir,
    _status_key,
    _RESPONSE_TTL_SECONDS,
    get_redis_client,
)


@pytest.fixture
def fake_redis():
    """각 테스트마다 격리된 fakeredis 인스턴스."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def sim_dir(tmp_path):
    d = tmp_path / "sim_alpha"
    d.mkdir()
    return str(d)


# ============================================================================
# 키 헬퍼
# ============================================================================

class TestKeyHelpers:
    def test_sim_id_from_dir_basic(self):
        assert _sim_id_from_dir("/var/data/sim_xyz") == "sim_xyz"

    def test_sim_id_from_dir_trailing_slash(self):
        assert _sim_id_from_dir("/var/data/sim_xyz/") == "sim_xyz"

    def test_cmd_queue_key(self):
        assert _cmd_queue_key("s1") == "mirofish:ipc:s1:cmd"

    def test_resp_key(self):
        assert _resp_key("s1", "abc") == "mirofish:ipc:s1:resp:abc"

    def test_status_key(self):
        assert _status_key("s1") == "mirofish:ipc:s1:status"


# ============================================================================
# get_redis_client (env 우선)
# ============================================================================

class TestGetRedisClient:
    def test_uses_env_var(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://example.invalid:6380/3")
        # 연결 자체는 lazy — 객체만 생성됨
        c = get_redis_client()
        # redis-py 의 connection_pool 에 db 가 포함됨
        assert c.connection_pool.connection_kwargs.get("db") == 3

    def test_explicit_url_overrides_env(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://example.invalid:1111/1")
        c = get_redis_client(url="redis://example.invalid:2222/2")
        assert c.connection_pool.connection_kwargs.get("db") == 2


# ============================================================================
# RedisSimulationIPCClient
# ============================================================================

class TestClientInit:
    def test_extracts_sim_id(self, sim_dir, fake_redis):
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        assert client.sim_id == "sim_alpha"


class TestClientSendCommand:
    def _drop_response(self, fake_redis, sim_id, command_id, status="completed",
                       result=None, error=None):
        """응답 LPUSH 헬퍼 (server 시뮬레이션)."""
        payload = json.dumps({
            "command_id": command_id,
            "status": status,
            "result": result,
            "error": error,
            "timestamp": "2026-05-01T00:00:00",
        })
        fake_redis.lpush(_resp_key(sim_id, command_id), payload)

    def test_happy_path_round_trip(self, sim_dir, fake_redis):
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)

        # watcher: 명령이 큐에 들어오면 즉시 응답 LPUSH
        seen_id = {}

        def _watcher():
            deadline = time.time() + 3.0
            while time.time() < deadline:
                payload = fake_redis.rpop(_cmd_queue_key("sim_alpha"))
                if payload:
                    cmd = json.loads(payload)
                    seen_id["id"] = cmd["command_id"]
                    self._drop_response(
                        fake_redis, "sim_alpha", cmd["command_id"],
                        result={"ok": True},
                    )
                    return
                time.sleep(0.01)

        t = threading.Thread(target=_watcher, daemon=True)
        t.start()
        resp = client.send_command(
            CommandType.INTERVIEW,
            {"agent_id": 1, "prompt": "hi"},
            timeout=3,
        )
        t.join(timeout=1.0)
        assert resp.status == CommandStatus.COMPLETED
        assert resp.result == {"ok": True}
        # BLPOP 이 응답을 소비했으므로 resp key 는 비어있음
        assert fake_redis.llen(_resp_key("sim_alpha", seen_id["id"])) == 0

    def test_timeout_raises(self, sim_dir, fake_redis):
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        with pytest.raises(TimeoutError):
            # 응답 없음 → BLPOP timeout 1초 (최소값으로 floor)
            client.send_command(CommandType.CLOSE_ENV, {}, timeout=1)

    def test_command_payload_is_lpush_then_rpop_fifo(self, sim_dir, fake_redis):
        """LPUSH (client) + RPOP (server) 조합으로 FIFO 보장."""
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        # send_command 는 BLPOP 대기에 묶이므로, 큐에만 들어가는지 별도 검증.
        # → command_id 를 만들고 직접 LPUSH 해서 RPOP 가 같은 걸 꺼내는지 확인.
        cmd = IPCCommand(
            command_id="c1",
            command_type=CommandType.INTERVIEW,
            args={"agent_id": 1, "prompt": "q"},
        )
        fake_redis.lpush(_cmd_queue_key("sim_alpha"), json.dumps(cmd.to_dict()))
        cmd2 = IPCCommand(
            command_id="c2",
            command_type=CommandType.INTERVIEW,
            args={"agent_id": 2, "prompt": "q2"},
        )
        fake_redis.lpush(_cmd_queue_key("sim_alpha"), json.dumps(cmd2.to_dict()))

        # RPOP 은 가장 먼저 LPUSH 된 것부터 (= c1)
        first = json.loads(fake_redis.rpop(_cmd_queue_key("sim_alpha")))
        second = json.loads(fake_redis.rpop(_cmd_queue_key("sim_alpha")))
        assert first["command_id"] == "c1"
        assert second["command_id"] == "c2"


class TestClientWrappers:
    def test_send_interview_passes_args(self, sim_dir, fake_redis, monkeypatch):
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        captured = {}

        def _send(command_type, args, timeout=60.0, poll_interval=0.5):
            captured["type"] = command_type
            captured["args"] = args
            captured["timeout"] = timeout
            return IPCResponse(command_id="x", status=CommandStatus.COMPLETED)

        monkeypatch.setattr(client, "send_command", _send)
        client.send_interview(agent_id=42, prompt="질문", platform="twitter", timeout=15.0)
        assert captured["type"] == CommandType.INTERVIEW
        assert captured["args"] == {"agent_id": 42, "prompt": "질문", "platform": "twitter"}
        assert captured["timeout"] == 15.0

    def test_send_interview_omits_platform_when_none(self, sim_dir, fake_redis, monkeypatch):
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        captured = {}

        def _send(command_type, args, timeout=60.0, poll_interval=0.5):
            captured["args"] = args
            return IPCResponse(command_id="x", status=CommandStatus.COMPLETED)

        monkeypatch.setattr(client, "send_command", _send)
        client.send_interview(agent_id=1, prompt="q")
        assert "platform" not in captured["args"]

    def test_send_batch_interview(self, sim_dir, fake_redis, monkeypatch):
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        captured = {}

        def _send(command_type, args, timeout=60.0, poll_interval=0.5):
            captured["type"] = command_type
            captured["args"] = args
            captured["timeout"] = timeout
            return IPCResponse(command_id="x", status=CommandStatus.COMPLETED)

        monkeypatch.setattr(client, "send_command", _send)
        items = [{"agent_id": 1, "prompt": "q1"}, {"agent_id": 2, "prompt": "q2"}]
        client.send_batch_interview(items, platform="reddit", timeout=200.0)
        assert captured["type"] == CommandType.BATCH_INTERVIEW
        assert captured["args"]["interviews"] == items
        assert captured["args"]["platform"] == "reddit"
        assert captured["timeout"] == 200.0

    def test_send_close_env(self, sim_dir, fake_redis, monkeypatch):
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        captured = {}

        def _send(command_type, args, timeout=60.0, poll_interval=0.5):
            captured["type"] = command_type
            captured["timeout"] = timeout
            return IPCResponse(command_id="x", status=CommandStatus.COMPLETED)

        monkeypatch.setattr(client, "send_command", _send)
        client.send_close_env(timeout=5.0)
        assert captured["type"] == CommandType.CLOSE_ENV
        assert captured["timeout"] == 5.0


class TestCheckEnvAlive:
    def test_missing_status(self, sim_dir, fake_redis):
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        assert client.check_env_alive() is False

    def test_alive(self, sim_dir, fake_redis):
        fake_redis.hset(_status_key("sim_alpha"), "status", "alive")
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        assert client.check_env_alive() is True

    def test_stopped(self, sim_dir, fake_redis):
        fake_redis.hset(_status_key("sim_alpha"), "status", "stopped")
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        assert client.check_env_alive() is False


# ============================================================================
# RedisSimulationIPCServer
# ============================================================================

class TestServerInit:
    def test_initial_running_false(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        assert server._running is False
        assert server.sim_id == "sim_alpha"


class TestServerStartStop:
    def test_start_writes_alive_status(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        server.start()
        assert server._running is True
        status = fake_redis.hgetall(_status_key("sim_alpha"))
        assert status["status"] == "alive"
        assert "timestamp" in status

    def test_stop_writes_stopped_status(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        server.start()
        server.stop()
        assert server._running is False
        status = fake_redis.hgetall(_status_key("sim_alpha"))
        assert status["status"] == "stopped"

    def test_update_status_with_platforms(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        server.update_status_with_platforms(
            status="alive", twitter_available=True, reddit_available=False
        )
        status = fake_redis.hgetall(_status_key("sim_alpha"))
        assert status["status"] == "alive"
        assert status["twitter_available"] == "true"
        assert status["reddit_available"] == "false"


class TestServerPollCommands:
    def _drop(self, fake_redis, command_id, command_type="interview", args=None):
        cmd = {
            "command_id": command_id,
            "command_type": command_type,
            "args": args or {},
            "timestamp": "2026-05-01T00:00:00",
        }
        fake_redis.lpush(_cmd_queue_key("sim_alpha"), json.dumps(cmd))

    def test_returns_none_when_empty(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        assert server.poll_commands() is None

    def test_returns_oldest_fifo(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        # client 가 LPUSH 하는 순서대로 → server 가 RPOP 으로 같은 순서 회수
        self._drop(fake_redis, "c1", args={"agent_id": 1})
        self._drop(fake_redis, "c2", args={"agent_id": 2})

        first = server.poll_commands()
        assert first is not None and first.command_id == "c1"
        second = server.poll_commands()
        assert second is not None and second.command_id == "c2"
        assert server.poll_commands() is None

    def test_atomic_single_consume(self, sim_dir, fake_redis):
        """LPOP atomic — 두 번 호출 시 동일 메시지가 반환되지 않음."""
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        self._drop(fake_redis, "only")
        first = server.poll_commands()
        second = server.poll_commands()
        assert first is not None and first.command_id == "only"
        assert second is None

    def test_corrupt_message_returns_none(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        # 손상된 JSON 직접 LPUSH
        fake_redis.lpush(_cmd_queue_key("sim_alpha"), "{not-json")
        assert server.poll_commands() is None

    def test_missing_field_returns_none(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        # 정상 JSON 이지만 from_dict 가 KeyError 낼 만한 메시지
        fake_redis.lpush(_cmd_queue_key("sim_alpha"), json.dumps({"foo": "bar"}))
        assert server.poll_commands() is None


class TestServerSendResponse:
    def test_writes_response_with_ttl(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        server.send_response(IPCResponse(
            command_id="cX",
            status=CommandStatus.COMPLETED,
            result={"answer": "ok"},
        ))
        # 응답이 list 에 들어가있고
        payload = fake_redis.rpop(_resp_key("sim_alpha", "cX"))
        assert payload is not None
        data = json.loads(payload)
        assert data["status"] == "completed"
        assert data["result"] == {"answer": "ok"}

    def test_response_has_ttl(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        server.send_response(IPCResponse(
            command_id="cT", status=CommandStatus.COMPLETED, result={}
        ))
        ttl = fake_redis.ttl(_resp_key("sim_alpha", "cT"))
        # 응답 key 의 TTL 이 _RESPONSE_TTL_SECONDS 근처 (수 초 오차 허용)
        assert 0 < ttl <= _RESPONSE_TTL_SECONDS

    def test_send_success_helper(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        server.send_success("c1", {"foo": "bar"})
        data = json.loads(fake_redis.rpop(_resp_key("sim_alpha", "c1")))
        assert data["status"] == "completed"
        assert data["result"] == {"foo": "bar"}
        assert data["error"] is None

    def test_send_error_helper(self, sim_dir, fake_redis):
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        server.send_error("c2", "총체적 실패")
        data = json.loads(fake_redis.rpop(_resp_key("sim_alpha", "c2")))
        assert data["status"] == "failed"
        assert data["error"] == "총체적 실패"
        assert data["result"] is None


# ============================================================================
# 통합: client ↔ server round-trip (fakeredis)
# ============================================================================

class TestClientServerRoundTrip:
    def test_full_round_trip_via_fake_redis(self, sim_dir, fake_redis):
        client = RedisSimulationIPCClient(sim_dir, redis_client=fake_redis)
        server = RedisSimulationIPCServer(sim_dir, redis_client=fake_redis)
        server.start()

        def _server_loop():
            deadline = time.time() + 3.0
            while time.time() < deadline:
                cmd = server.poll_commands()
                if cmd:
                    server.send_success(cmd.command_id, {"echo": cmd.args})
                    return
                time.sleep(0.01)

        t = threading.Thread(target=_server_loop, daemon=True)
        t.start()
        # send_command 는 BLPOP timeout 최소 1초로 floor
        resp = client.send_interview(agent_id=42, prompt="안녕", timeout=3)
        t.join(timeout=1.0)
        assert resp.status == CommandStatus.COMPLETED
        assert resp.result == {"echo": {"agent_id": 42, "prompt": "안녕"}}
        server.stop()
