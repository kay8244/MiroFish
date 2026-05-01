"""
Redis 기반 시뮬레이션 IPC (TODOS #2)

파일 IPC (`simulation_ipc.py`) 의 경쟁조건을 근본 해결하기 위한 대체 구현.
인터페이스는 `SimulationIPCClient` / `SimulationIPCServer` 와 동일하므로 호출자 코드는
한 줄 교체만으로 전환된다.

키 컨벤션 (per `sim_id`):
  - cmd queue:   `mirofish:ipc:{sim_id}:cmd`            (LPUSH client → LPOP server, FIFO)
  - response:    `mirofish:ipc:{sim_id}:resp:{cmd_id}`  (server LPUSH → client BLPOP, single-shot)
  - status hash: `mirofish:ipc:{sim_id}:status`         (server HSET, client HGET)

원자성 보장:
  - LPOP 은 atomic — 두 server poller 가 동시에 호출해도 double-consume 없음.
  - BLPOP 은 정확히 한 번만 응답을 받음 (response key 는 응답 직후 삭제됨).
  - 응답 key TTL 300s — 클라이언트 timeout 후 누적 방지.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis

from ..utils.logger import get_logger
from .simulation_ipc import (
    CommandStatus,
    CommandType,
    IPCCommand,
    IPCResponse,
)

logger = get_logger('mirofish.simulation_ipc_redis')

# 키 prefix — 다른 앱과 충돌 방지
_KEY_PREFIX = "mirofish:ipc"

# 응답 key TTL — 클라이언트 timeout 시 응답 누적 방지
_RESPONSE_TTL_SECONDS = 300

# 시뮬레이션 ID 추출: simulation_dir 의 마지막 컴포넌트
def _sim_id_from_dir(simulation_dir: str) -> str:
    return os.path.basename(os.path.normpath(simulation_dir))


def _cmd_queue_key(sim_id: str) -> str:
    return f"{_KEY_PREFIX}:{sim_id}:cmd"


def _resp_key(sim_id: str, command_id: str) -> str:
    return f"{_KEY_PREFIX}:{sim_id}:resp:{command_id}"


def _status_key(sim_id: str) -> str:
    return f"{_KEY_PREFIX}:{sim_id}:status"


def get_redis_client(url: Optional[str] = None) -> redis.Redis:
    """
    Redis 클라이언트 팩토리.

    `url` 없으면 `REDIS_URL` env 사용. 둘 다 없으면 기본 `redis://localhost:6379/0`.
    `decode_responses=True` 로 bytes ↔ str 자동 변환 (json.loads/dumps 와 호환).
    """
    redis_url = url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(redis_url, decode_responses=True)


class RedisSimulationIPCClient:
    """
    Redis 기반 IPC 클라이언트 (Flask 측).

    `SimulationIPCClient` 와 동일한 시그니처로 drop-in 교체 가능.
    """

    def __init__(
        self,
        simulation_dir: str,
        redis_client: Optional[redis.Redis] = None,
    ):
        self.simulation_dir = simulation_dir
        self.sim_id = _sim_id_from_dir(simulation_dir)
        self._redis = redis_client or get_redis_client()

    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5,  # 호환용 — Redis 경로에서는 사용하지 않음
    ) -> IPCResponse:
        """
        명령 전송 + 응답 BLPOP 으로 대기.

        Raises:
            TimeoutError: timeout 초 내 응답 없음
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args,
        )

        cmd_key = _cmd_queue_key(self.sim_id)
        resp_key = _resp_key(self.sim_id, command_id)

        # 명령을 큐에 넣고 응답 key 를 BLPOP (단일 shot)
        # NOTE: 응답 key TTL 은 server 측에서 LPUSH 후에 EXPIRE 로 설정. 여기선
        # 클라이언트가 정상적으로 BLPOP 하면 즉시 받고, timeout 시엔 server 가
        # 나중에 LPUSH 한 응답이 TTL 로 자동 정리됨.
        self._redis.lpush(cmd_key, json.dumps(command.to_dict(), ensure_ascii=False))
        logger.info(
            f"IPC 명령 전송 (redis): {command_type.value}, "
            f"command_id={command_id}, sim_id={self.sim_id}"
        )

        # BLPOP timeout 은 정수 초 (0 = 무한). 안전하게 ceil 처리.
        # timeout < 1 인 경우에도 최소 1초 대기 — 호출자 timeout 보다 짧지 않게.
        blpop_timeout = max(1, int(round(timeout)))
        result = self._redis.blpop(resp_key, timeout=blpop_timeout)
        if result is None:
            logger.error(
                f"IPC 응답 대기 시간 초과 (redis): command_id={command_id}, "
                f"timeout={timeout}s"
            )
            raise TimeoutError(f"명령 응답 대기 시간 초과 ({timeout}초)")

        # BLPOP 은 (key, value) tuple 반환
        _, payload = result
        try:
            response_data = json.loads(payload)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"응답 파싱 실패 (redis): {e}, payload={payload!r}")
            raise

        response = IPCResponse.from_dict(response_data)
        logger.info(
            f"IPC 응답 수신 (redis): command_id={command_id}, "
            f"status={response.status.value}"
        )
        return response

    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: Optional[str] = None,
        timeout: float = 60.0,
    ) -> IPCResponse:
        args: Dict[str, Any] = {"agent_id": agent_id, "prompt": prompt}
        if platform:
            args["platform"] = platform
        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout,
        )

    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: Optional[str] = None,
        timeout: float = 120.0,
    ) -> IPCResponse:
        args: Dict[str, Any] = {"interviews": interviews}
        if platform:
            args["platform"] = platform
        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout,
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout,
        )

    def check_env_alive(self) -> bool:
        """
        시뮬레이션 환경 생존 여부 확인.

        status hash 의 `status` 필드가 'alive' 인지 확인.
        """
        status = self._redis.hget(_status_key(self.sim_id), "status")
        return status == "alive"


class RedisSimulationIPCServer:
    """
    Redis 기반 IPC 서버 (시뮬레이션 서브프로세스 측).

    `SimulationIPCServer` 와 동일한 시그니처로 drop-in 교체 가능.
    """

    def __init__(
        self,
        simulation_dir: str,
        redis_client: Optional[redis.Redis] = None,
    ):
        self.simulation_dir = simulation_dir
        self.sim_id = _sim_id_from_dir(simulation_dir)
        self._redis = redis_client or get_redis_client()
        self._running = False

    def start(self) -> None:
        """서버 실행 상태 표시 — status hash 갱신."""
        self._running = True
        self._update_env_status("alive")

    def stop(self) -> None:
        """서버 중지 상태 표시 — status hash 갱신."""
        self._running = False
        self._update_env_status("stopped")

    def _update_env_status(
        self,
        status: str,
        twitter_available: Optional[bool] = None,
        reddit_available: Optional[bool] = None,
    ) -> None:
        """status hash 원자적 업데이트 (HSET 다중 필드 = 1 명령 = 원자)."""
        fields: Dict[str, str] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }
        if twitter_available is not None:
            fields["twitter_available"] = "true" if twitter_available else "false"
        if reddit_available is not None:
            fields["reddit_available"] = "true" if reddit_available else "false"
        # mapping 기반 hset (redis-py 5+ 시그니처)
        self._redis.hset(_status_key(self.sim_id), mapping=fields)

    def update_status_with_platforms(
        self,
        status: str,
        twitter_available: bool,
        reddit_available: bool,
    ) -> None:
        """플랫폼 가용성 포함 status 갱신 (parallel sim 스크립트용)."""
        self._update_env_status(
            status=status,
            twitter_available=twitter_available,
            reddit_available=reddit_available,
        )

    def poll_commands(self) -> Optional[IPCCommand]:
        """
        명령 큐에서 다음 명령을 atomic 하게 꺼내 반환.

        파일 IPC 의 commands/.processing/ 격리는 불필요 — Redis LPOP 자체가 atomic.
        FIFO 보장: 클라이언트가 LPUSH, 서버가 RPOP (== queue 의미).
        """
        cmd_key = _cmd_queue_key(self.sim_id)
        payload = self._redis.rpop(cmd_key)
        if payload is None:
            return None
        try:
            data = json.loads(payload)
            return IPCCommand.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # 손상된 메시지는 버린다 (file IPC 의 orphan 과 동일한 의미)
            logger.warning(f"명령 파싱 실패 (redis): {e}, payload={payload!r}")
            return None

    def send_response(self, response: IPCResponse) -> None:
        """
        응답을 atomic 하게 전송: LPUSH + EXPIRE.

        LPUSH 후 EXPIRE 사이에 클라이언트가 BLPOP 으로 가져가도 안전 — 이미 비어있는
        list 에 EXPIRE 거는 건 무해 (key 가 없으면 아무 일도 안 일어남).
        """
        resp_key = _resp_key(self.sim_id, response.command_id)
        payload = json.dumps(response.to_dict(), ensure_ascii=False)
        # pipeline 으로 LPUSH + EXPIRE 를 한 라운드트립에 — 원자성보다 효율 목적
        pipe = self._redis.pipeline()
        pipe.lpush(resp_key, payload)
        pipe.expire(resp_key, _RESPONSE_TTL_SECONDS)
        pipe.execute()

    def send_success(self, command_id: str, result: Dict[str, Any]) -> None:
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result,
        ))

    def send_error(self, command_id: str, error: str) -> None:
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error,
        ))


__all__ = [
    "RedisSimulationIPCClient",
    "RedisSimulationIPCServer",
    "get_redis_client",
]
