"""
시뮬레이션 IPC 백엔드 선택 팩토리 (TODOS #2).

`REDIS_URL` 환경변수가 설정되어 있으면 Redis IPC, 없으면 기존 파일 IPC 를 반환한다.
점진 마이그레이션 동안 두 경로가 같은 인터페이스를 갖도록 보장.

호출자 코드 (simulation_runner) 는:
    ipc_client = make_ipc_client(sim_dir)
한 줄로 백엔드를 알아서 선택. Drop-in.
"""

from __future__ import annotations

import os
from typing import Union

from ..utils.logger import get_logger
from .simulation_ipc import SimulationIPCClient, SimulationIPCServer

logger = get_logger('mirofish.simulation_ipc_factory')


# 한 번 결정한 백엔드는 프로세스 라이프타임 동안 일관성 유지 (로그 1회만 찍기 위해)
_logged_backend = False


def _should_use_redis() -> bool:
    """REDIS_URL 이 빈 문자열이 아니어야 Redis 사용."""
    url = os.environ.get("REDIS_URL", "").strip()
    return bool(url)


def make_ipc_client(simulation_dir: str):
    """
    Flask 측 IPC 클라이언트 생성.

    Returns:
        REDIS_URL 설정 시 RedisSimulationIPCClient,
        아니면 SimulationIPCClient (file IPC).
    """
    global _logged_backend
    if _should_use_redis():
        # 지연 import — Redis 미사용 환경에서 redis 라이브러리 import 안 함
        from .simulation_ipc_redis import RedisSimulationIPCClient
        if not _logged_backend:
            logger.info(f"IPC 백엔드: Redis ({os.environ.get('REDIS_URL')})")
            _logged_backend = True
        return RedisSimulationIPCClient(simulation_dir)
    if not _logged_backend:
        logger.info("IPC 백엔드: 파일시스템 (REDIS_URL 미설정)")
        _logged_backend = True
    return SimulationIPCClient(simulation_dir)


def make_ipc_server(simulation_dir: str):
    """
    시뮬레이션 서브프로세스 측 IPC 서버 생성.

    Returns:
        REDIS_URL 설정 시 RedisSimulationIPCServer,
        아니면 SimulationIPCServer (file IPC).
    """
    if _should_use_redis():
        from .simulation_ipc_redis import RedisSimulationIPCServer
        return RedisSimulationIPCServer(simulation_dir)
    return SimulationIPCServer(simulation_dir)


__all__ = [
    "make_ipc_client",
    "make_ipc_server",
]
