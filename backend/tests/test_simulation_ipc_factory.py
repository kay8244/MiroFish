"""
시뮬레이션 IPC 백엔드 팩토리 테스트 (`app/services/simulation_ipc_factory.py`).

REDIS_URL 환경변수 유무에 따라 Redis IPC vs file IPC 가 선택되는지만 검증.
실제 동작 검증은 각 백엔드의 단위 테스트가 따로 담당.
"""

from __future__ import annotations

import importlib

import pytest

from app.services import simulation_ipc_factory
from app.services.simulation_ipc import SimulationIPCClient, SimulationIPCServer
from app.services.simulation_ipc_redis import (
    RedisSimulationIPCClient,
    RedisSimulationIPCServer,
)


@pytest.fixture(autouse=True)
def reset_logged_flag():
    """팩토리의 _logged_backend 플래그 초기화 (테스트 격리)."""
    simulation_ipc_factory._logged_backend = False
    yield
    simulation_ipc_factory._logged_backend = False


class TestMakeIpcClient:
    def test_no_redis_url_returns_file_client(self, monkeypatch, tmp_path):
        monkeypatch.delenv("REDIS_URL", raising=False)
        c = simulation_ipc_factory.make_ipc_client(str(tmp_path / "sim"))
        assert isinstance(c, SimulationIPCClient)

    def test_empty_redis_url_returns_file_client(self, monkeypatch, tmp_path):
        # 빈 문자열도 file 경로
        monkeypatch.setenv("REDIS_URL", "")
        c = simulation_ipc_factory.make_ipc_client(str(tmp_path / "sim"))
        assert isinstance(c, SimulationIPCClient)

    def test_redis_url_returns_redis_client(self, monkeypatch, tmp_path):
        # 실제 연결은 lazy — 객체 생성만 됨 (host 도달 불가해도 OK)
        monkeypatch.setenv("REDIS_URL", "redis://example.invalid:6379/0")
        c = simulation_ipc_factory.make_ipc_client(str(tmp_path / "sim"))
        assert isinstance(c, RedisSimulationIPCClient)

    def test_whitespace_url_treated_as_empty(self, monkeypatch, tmp_path):
        monkeypatch.setenv("REDIS_URL", "   ")
        c = simulation_ipc_factory.make_ipc_client(str(tmp_path / "sim"))
        assert isinstance(c, SimulationIPCClient)


class TestMakeIpcServer:
    def test_no_redis_url_returns_file_server(self, monkeypatch, tmp_path):
        monkeypatch.delenv("REDIS_URL", raising=False)
        s = simulation_ipc_factory.make_ipc_server(str(tmp_path / "sim"))
        assert isinstance(s, SimulationIPCServer)

    def test_redis_url_returns_redis_server(self, monkeypatch, tmp_path):
        monkeypatch.setenv("REDIS_URL", "redis://example.invalid:6379/0")
        s = simulation_ipc_factory.make_ipc_server(str(tmp_path / "sim"))
        assert isinstance(s, RedisSimulationIPCServer)
