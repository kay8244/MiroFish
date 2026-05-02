"""
SimulationIPC 단위 테스트 (`app/services/simulation_ipc.py`).

파일시스템 기반 명령/응답 IPC. 검증 단위:
- `_atomic_write_json`: tmp → rename, 실패 시 tmp 정리
- IPCCommand / IPCResponse: to_dict / from_dict 라운드트립
- SimulationIPCClient: send_command 폴링 + 타임아웃 + 정리, 래퍼 메서드, check_env_alive
- SimulationIPCServer: 디렉토리 준비, start/stop, poll_commands (race 방지), send_response 정리
"""

import json
import os
import threading
import time

import pytest

from app.services.simulation_ipc import (
    CommandStatus,
    CommandType,
    IPCCommand,
    IPCResponse,
    SimulationIPCClient,
    SimulationIPCServer,
    _atomic_write_json,
    _PROCESSING_SUBDIR,
)


# ============================================================================
# _atomic_write_json
# ============================================================================

class TestAtomicWriteJSON:
    def test_writes_payload(self, tmp_path):
        target = tmp_path / "out.json"
        _atomic_write_json(str(target), {"k": "v", "ko": "한글"})
        assert target.exists()
        with open(target, encoding="utf-8") as f:
            assert json.load(f) == {"k": "v", "ko": "한글"}

    def test_no_tmp_files_left(self, tmp_path):
        target = tmp_path / "out.json"
        _atomic_write_json(str(target), {"a": 1})
        leftover = [p.name for p in tmp_path.iterdir() if p.name != "out.json"]
        assert leftover == []

    def test_cleans_tmp_on_failure(self, tmp_path, monkeypatch):
        target = tmp_path / "out.json"
        # os.replace 실패 시 tmp 정리되는지
        def _boom(*a, **kw):
            raise OSError("simulated rename failure")
        monkeypatch.setattr(os, "replace", _boom)
        with pytest.raises(OSError):
            _atomic_write_json(str(target), {"a": 1})
        # tmp 정리되어 디렉토리 비어있어야 함
        assert list(tmp_path.iterdir()) == []


# ============================================================================
# IPCCommand / IPCResponse
# ============================================================================

class TestIPCCommandDataclass:
    def test_to_dict(self):
        cmd = IPCCommand(
            command_id="c1",
            command_type=CommandType.INTERVIEW,
            args={"agent_id": 1},
            timestamp="2026-05-01T00:00:00",
        )
        assert cmd.to_dict() == {
            "command_id": "c1",
            "command_type": "interview",
            "args": {"agent_id": 1},
            "timestamp": "2026-05-01T00:00:00",
        }

    def test_from_dict_roundtrip(self):
        original = IPCCommand(
            command_id="c2",
            command_type=CommandType.BATCH_INTERVIEW,
            args={"interviews": []},
            timestamp="2026-05-01T01:00:00",
        )
        restored = IPCCommand.from_dict(original.to_dict())
        assert restored.command_id == "c2"
        assert restored.command_type == CommandType.BATCH_INTERVIEW
        assert restored.args == {"interviews": []}
        assert restored.timestamp == "2026-05-01T01:00:00"

    def test_from_dict_default_args(self):
        cmd = IPCCommand.from_dict(
            {"command_id": "c3", "command_type": "close_env"}
        )
        assert cmd.args == {}


class TestIPCResponseDataclass:
    def test_to_dict_completed(self):
        r = IPCResponse(
            command_id="c1",
            status=CommandStatus.COMPLETED,
            result={"answer": "hi"},
            timestamp="2026-05-01T00:00:00",
        )
        assert r.to_dict() == {
            "command_id": "c1",
            "status": "completed",
            "result": {"answer": "hi"},
            "error": None,
            "timestamp": "2026-05-01T00:00:00",
        }

    def test_from_dict_roundtrip_failed(self):
        original = IPCResponse(
            command_id="c2",
            status=CommandStatus.FAILED,
            error="boom",
            timestamp="2026-05-01T02:00:00",
        )
        restored = IPCResponse.from_dict(original.to_dict())
        assert restored.status == CommandStatus.FAILED
        assert restored.error == "boom"
        assert restored.result is None


# ============================================================================
# SimulationIPCClient
# ============================================================================

class TestClientInit:
    def test_creates_dirs(self, tmp_path):
        sim_dir = tmp_path / "sim_x"
        SimulationIPCClient(str(sim_dir))
        assert (sim_dir / "ipc_commands").is_dir()
        assert (sim_dir / "ipc_responses").is_dir()


class TestClientSendCommand:
    def _drop_response(self, sim_dir, command_id, status="completed", result=None, error=None):
        """테스트 헬퍼 — 가짜 응답 파일을 responses/ 에 작성."""
        path = os.path.join(str(sim_dir), "ipc_responses", f"{command_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "command_id": command_id,
                "status": status,
                "result": result,
                "error": error,
                "timestamp": "2026-05-01T00:00:00",
            }, f)

    def test_happy_path_returns_response_and_cleans_files(self, tmp_path):
        sim_dir = tmp_path / "sim"
        client = SimulationIPCClient(str(sim_dir))

        # 워처: command 파일이 떨어지면 즉시 응답을 작성
        seen_id = {}

        def _watcher():
            deadline = time.time() + 3.0
            while time.time() < deadline:
                files = [
                    p for p in (sim_dir / "ipc_commands").iterdir()
                    if p.is_file() and p.suffix == ".json"
                ]
                if files:
                    cmd_id = files[0].stem
                    seen_id["id"] = cmd_id
                    self._drop_response(sim_dir, cmd_id, result={"ok": True})
                    return
                time.sleep(0.01)

        t = threading.Thread(target=_watcher, daemon=True)
        t.start()

        resp = client.send_command(
            CommandType.INTERVIEW,
            {"agent_id": 7, "prompt": "안녕"},
            timeout=3.0,
            poll_interval=0.05,
        )
        t.join(timeout=1.0)
        assert resp.status == CommandStatus.COMPLETED
        assert resp.result == {"ok": True}
        # command + response 파일 모두 삭제됨
        cmd_path = sim_dir / "ipc_commands" / f"{seen_id['id']}.json"
        resp_path = sim_dir / "ipc_responses" / f"{seen_id['id']}.json"
        assert not cmd_path.exists()
        assert not resp_path.exists()

    def test_timeout_raises_and_cleans_command(self, tmp_path):
        sim_dir = tmp_path / "sim"
        client = SimulationIPCClient(str(sim_dir))

        with pytest.raises(TimeoutError):
            # 응답 안 떨굼 → 짧은 timeout 으로 빠르게 종료
            client.send_command(
                CommandType.CLOSE_ENV, {}, timeout=0.1, poll_interval=0.05
            )

        # 타임아웃 후 command 파일 정리 — commands/ 디렉토리는 비어 있어야 함
        cmd_files = list((sim_dir / "ipc_commands").glob("*.json"))
        assert cmd_files == []

    def test_bad_response_json_then_good_json_succeeds(self, tmp_path):
        """망가진 JSON 응답이 있어도 client는 폴링을 계속해 결국 정상 응답을 받음."""
        sim_dir = tmp_path / "sim"
        client = SimulationIPCClient(str(sim_dir))

        def _watcher():
            deadline = time.time() + 3.0
            wrote_bad = False
            while time.time() < deadline:
                files = [
                    p for p in (sim_dir / "ipc_commands").iterdir()
                    if p.is_file() and p.suffix == ".json"
                ]
                if files:
                    cmd_id = files[0].stem
                    resp_path = sim_dir / "ipc_responses" / f"{cmd_id}.json"
                    if not wrote_bad:
                        # 첫 라운드: 망가진 JSON
                        with open(resp_path, "w") as f:
                            f.write("{not-json")
                        wrote_bad = True
                        time.sleep(0.1)
                        # 두 번째 라운드: 정상 JSON 으로 덮어쓰기
                        self._drop_response(
                            sim_dir, cmd_id, result={"after_recovery": True}
                        )
                        return
                time.sleep(0.01)

        t = threading.Thread(target=_watcher, daemon=True)
        t.start()

        resp = client.send_command(
            CommandType.INTERVIEW, {"agent_id": 1, "prompt": "x"},
            timeout=3.0, poll_interval=0.05,
        )
        t.join(timeout=1.0)
        assert resp.status == CommandStatus.COMPLETED
        assert resp.result == {"after_recovery": True}


class TestClientWrappers:
    def test_send_interview_passes_args(self, tmp_path, monkeypatch):
        client = SimulationIPCClient(str(tmp_path / "sim"))
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

    def test_send_interview_omits_platform_when_none(self, tmp_path, monkeypatch):
        client = SimulationIPCClient(str(tmp_path / "sim"))
        captured = {}

        def _send(command_type, args, timeout=60.0, poll_interval=0.5):
            captured["args"] = args
            return IPCResponse(command_id="x", status=CommandStatus.COMPLETED)

        monkeypatch.setattr(client, "send_command", _send)
        client.send_interview(agent_id=1, prompt="q")
        assert "platform" not in captured["args"]

    def test_send_batch_interview(self, tmp_path, monkeypatch):
        client = SimulationIPCClient(str(tmp_path / "sim"))
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

    def test_send_close_env(self, tmp_path, monkeypatch):
        client = SimulationIPCClient(str(tmp_path / "sim"))
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
    def test_missing_status_file(self, tmp_path):
        client = SimulationIPCClient(str(tmp_path / "sim"))
        assert client.check_env_alive() is False

    def test_alive(self, tmp_path):
        sim_dir = tmp_path / "sim"
        client = SimulationIPCClient(str(sim_dir))
        with open(sim_dir / "env_status.json", "w") as f:
            json.dump({"status": "alive"}, f)
        assert client.check_env_alive() is True

    def test_stopped(self, tmp_path):
        sim_dir = tmp_path / "sim"
        client = SimulationIPCClient(str(sim_dir))
        with open(sim_dir / "env_status.json", "w") as f:
            json.dump({"status": "stopped"}, f)
        assert client.check_env_alive() is False

    def test_corrupt_json(self, tmp_path):
        sim_dir = tmp_path / "sim"
        client = SimulationIPCClient(str(sim_dir))
        with open(sim_dir / "env_status.json", "w") as f:
            f.write("{not-json")
        assert client.check_env_alive() is False


# ============================================================================
# SimulationIPCServer
# ============================================================================

class TestServerInit:
    def test_creates_dirs(self, tmp_path):
        sim_dir = tmp_path / "sim_s"
        server = SimulationIPCServer(str(sim_dir))
        assert (sim_dir / "ipc_commands").is_dir()
        assert (sim_dir / "ipc_responses").is_dir()
        assert (sim_dir / "ipc_commands" / _PROCESSING_SUBDIR).is_dir()
        assert server._running is False


class TestServerStartStop:
    def test_start_writes_alive_status(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        server.start()
        assert server._running is True
        with open(sim_dir / "env_status.json", encoding="utf-8") as f:
            data = json.load(f)
        assert data["status"] == "alive"
        assert "timestamp" in data

    def test_stop_writes_stopped_status(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        server.start()
        server.stop()
        assert server._running is False
        with open(sim_dir / "env_status.json", encoding="utf-8") as f:
            data = json.load(f)
        assert data["status"] == "stopped"


class TestServerPollCommands:
    def _drop_command(self, sim_dir, command_id, command_type="interview", args=None):
        cmd = {
            "command_id": command_id,
            "command_type": command_type,
            "args": args or {},
            "timestamp": "2026-05-01T00:00:00",
        }
        path = os.path.join(
            str(sim_dir), "ipc_commands", f"{command_id}.json"
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cmd, f)
        return path

    def test_returns_none_when_empty(self, tmp_path):
        server = SimulationIPCServer(str(tmp_path / "sim"))
        assert server.poll_commands() is None

    def test_returns_oldest_command_and_moves_to_processing(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        # 시간순 (mtime 차이) 으로 두 개 떨굼
        p1 = self._drop_command(sim_dir, "c1", args={"agent_id": 1, "prompt": "q1"})
        os.utime(p1, (1000, 1000))
        p2 = self._drop_command(sim_dir, "c2", args={"agent_id": 2, "prompt": "q2"})
        os.utime(p2, (2000, 2000))

        cmd = server.poll_commands()
        assert cmd is not None
        assert cmd.command_id == "c1"
        # 원래 자리에서 사라지고 processing/ 로 이동
        assert not (sim_dir / "ipc_commands" / "c1.json").exists()
        assert (sim_dir / "ipc_commands" / _PROCESSING_SUBDIR / "c1.json").exists()
        # c2 는 그대로
        assert (sim_dir / "ipc_commands" / "c2.json").exists()

    def test_double_poll_returns_next(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        self._drop_command(sim_dir, "c1")
        self._drop_command(sim_dir, "c2")

        first = server.poll_commands()
        second = server.poll_commands()
        # 둘 다 하나씩 가져갔으니 이제 None
        third = server.poll_commands()
        assert {first.command_id, second.command_id} == {"c1", "c2"}
        assert third is None

    def test_ignores_processing_subdir_files(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        # processing/ 에 직접 떨궈도 poll 결과에 안 잡혀야 함
        proc_path = (
            sim_dir / "ipc_commands" / _PROCESSING_SUBDIR / "old.json"
        )
        with open(proc_path, "w") as f:
            json.dump({
                "command_id": "old",
                "command_type": "interview",
                "args": {},
            }, f)
        assert server.poll_commands() is None

    def test_skips_non_json_files(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        with open(sim_dir / "ipc_commands" / "not.txt", "w") as f:
            f.write("ignore me")
        assert server.poll_commands() is None

    def test_corrupt_command_returns_none_and_keeps_in_processing(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        bad_path = sim_dir / "ipc_commands" / "bad.json"
        with open(bad_path, "w") as f:
            f.write("{not-json")
        result = server.poll_commands()
        assert result is None
        # processing/ 에 orphan 으로 남음
        assert (sim_dir / "ipc_commands" / _PROCESSING_SUBDIR / "bad.json").exists()


class TestServerSendResponse:
    def _drop_to_processing(self, sim_dir, command_id):
        proc = sim_dir / "ipc_commands" / _PROCESSING_SUBDIR / f"{command_id}.json"
        with open(proc, "w") as f:
            json.dump({"command_id": command_id, "command_type": "interview"}, f)
        return proc

    def test_writes_response_and_removes_from_processing(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        proc = self._drop_to_processing(sim_dir, "cX")
        server.send_response(IPCResponse(
            command_id="cX",
            status=CommandStatus.COMPLETED,
            result={"answer": "ok"},
        ))
        # 응답 작성됨
        resp_path = sim_dir / "ipc_responses" / "cX.json"
        assert resp_path.exists()
        with open(resp_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["status"] == "completed"
        assert data["result"] == {"answer": "ok"}
        # processing/ 에서 명령 파일 정리
        assert not proc.exists()

    def test_falls_back_to_commands_dir_for_cleanup(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        # commands/ 에만 남아있는 케이스 (poll 안 거친 흐름)
        cmd_path = sim_dir / "ipc_commands" / "cY.json"
        with open(cmd_path, "w") as f:
            json.dump({"command_id": "cY"}, f)

        server.send_response(IPCResponse(
            command_id="cY", status=CommandStatus.FAILED, error="x"
        ))
        assert (sim_dir / "ipc_responses" / "cY.json").exists()
        assert not cmd_path.exists()

    def test_send_success_helper(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        server.send_success("c1", {"foo": "bar"})
        with open(sim_dir / "ipc_responses" / "c1.json") as f:
            data = json.load(f)
        assert data["status"] == "completed"
        assert data["result"] == {"foo": "bar"}
        assert data["error"] is None

    def test_send_error_helper(self, tmp_path):
        sim_dir = tmp_path / "sim"
        server = SimulationIPCServer(str(sim_dir))
        server.send_error("c2", "총체적 실패")
        with open(sim_dir / "ipc_responses" / "c2.json") as f:
            data = json.load(f)
        assert data["status"] == "failed"
        assert data["error"] == "총체적 실패"
        assert data["result"] is None
