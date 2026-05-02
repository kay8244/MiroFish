"""
시뮬레이션 IPC 통신 모듈
Flask 백엔드와 시뮬레이션 스크립트 간의 프로세스 간 통신

파일 시스템을 통한 간단한 명령/응답 패턴 구현:
1. Flask가 commands/ 디렉토리에 명령 파일 작성
2. 시뮬레이션 스크립트가 명령 디렉토리를 폴링하여 명령 실행 후 responses/ 디렉토리에 응답 작성
3. Flask가 응답 디렉토리를 폴링하여 결과 가져오기
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.logger import get_logger

logger = get_logger('mirofish.simulation_ipc')

# 읽기 중인 명령을 이동시키는 서브디렉토리 — double-consume 방지용
_PROCESSING_SUBDIR = ".processing"


def _atomic_write_json(filepath: str, data: Dict[str, Any]) -> None:
    """tmp 파일에 쓴 뒤 원자적 rename — torn read 방지 (POSIX os.replace)"""
    tmp_path = f"{filepath}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


class CommandType(str, Enum):
    """명령 유형"""
    INTERVIEW = "interview"           # 단일 Agent 인터뷰
    BATCH_INTERVIEW = "batch_interview"  # 일괄 인터뷰
    CLOSE_ENV = "close_env"           # 환경 종료


class CommandStatus(str, Enum):
    """명령 상태"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """IPC 명령"""
    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCCommand':
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class IPCResponse:
    """IPC 응답"""
    command_id: str
    status: CommandStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCResponse':
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class SimulationIPCClient:
    """
    시뮬레이션 IPC 클라이언트 (Flask 측 사용)

    시뮬레이션 프로세스에 명령을 전송하고 응답을 대기
    """

    def __init__(self, simulation_dir: str):
        """
        IPC 클라이언트 초기화

        Args:
            simulation_dir: 시뮬레이션 데이터 디렉토리
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")

        # 디렉토리 존재 확인
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5
    ) -> IPCResponse:
        """
        명령 전송 및 응답 대기

        Args:
            command_type: 명령 유형
            args: 명령 파라미터
            timeout: 타임아웃 시간 (초)
            poll_interval: 폴링 간격 (초)

        Returns:
            IPCResponse

        Raises:
            TimeoutError: 응답 대기 시간 초과
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args
        )

        # 명령 파일 원자적 작성 (tmp → rename)
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        _atomic_write_json(command_file, command.to_dict())

        logger.info(f"IPC 명령 전송: {command_type.value}, command_id={command_id}")

        # 응답 대기
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', encoding='utf-8') as f:
                        response_data = json.load(f)
                    response = IPCResponse.from_dict(response_data)

                    # 명령 및 응답 파일 정리
                    try:
                        os.remove(command_file)
                        os.remove(response_file)
                    except OSError:
                        pass

                    logger.info(f"IPC 응답 수신: command_id={command_id}, status={response.status.value}")
                    return response
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"응답 파싱 실패: {e}")

            time.sleep(poll_interval)

        # 타임아웃
        logger.error(f"IPC 응답 대기 시간 초과: command_id={command_id}")

        # 명령 파일 정리
        try:
            os.remove(command_file)
        except OSError:
            pass

        raise TimeoutError(f"명령 응답 대기 시간 초과 ({timeout}초)")

    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> IPCResponse:
        """
        단일 Agent 인터뷰 명령 전송

        Args:
            agent_id: Agent ID
            prompt: 인터뷰 질문
            platform: 지정 플랫폼 (선택적)
                - "twitter": Twitter 플랫폼만 인터뷰
                - "reddit": Reddit 플랫폼만 인터뷰
                - None: 양대 플랫폼 시뮬레이션 시 두 플랫폼 동시 인터뷰, 단일 플랫폼 시 해당 플랫폼 인터뷰
            timeout: 타임아웃 시간

        Returns:
            IPCResponse, result 필드에 인터뷰 결과 포함
        """
        args = {
            "agent_id": agent_id,
            "prompt": prompt
        }
        if platform:
            args["platform"] = platform

        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> IPCResponse:
        """
        일괄 인터뷰 명령 전송

        Args:
            interviews: 인터뷰 목록, 각 항목은 {"agent_id": int, "prompt": str, "platform": str(선택적)} 포함
            platform: 기본 플랫폼 (선택적, 각 인터뷰 항목의 platform으로 덮어쓰기 가능)
                - "twitter": 기본적으로 Twitter 플랫폼만 인터뷰
                - "reddit": 기본적으로 Reddit 플랫폼만 인터뷰
                - None: 양대 플랫폼 시뮬레이션 시 각 Agent를 두 플랫폼에서 동시 인터뷰
            timeout: 타임아웃 시간

        Returns:
            IPCResponse, result 필드에 모든 인터뷰 결과 포함
        """
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform

        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """
        환경 종료 명령 전송

        Args:
            timeout: 타임아웃 시간

        Returns:
            IPCResponse
        """
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout
        )

    def check_env_alive(self) -> bool:
        """
        시뮬레이션 환경 생존 여부 확인

        env_status.json 파일 확인을 통해 판단
        """
        return self.get_env_status().get("status") == "alive"

    def get_env_status(self) -> Dict[str, Any]:
        """
        env_status.json 의 전체 필드 반환 (없으면 기본값).
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        if not os.path.exists(status_file):
            return {"status": "stopped", "timestamp": None}
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"status": "stopped", "timestamp": None}


class SimulationIPCServer:
    """
    시뮬레이션 IPC 서버 (시뮬레이션 스크립트 측 사용)

    명령 디렉토리를 폴링하여 명령 실행 후 응답 반환
    """

    def __init__(self, simulation_dir: str):
        """
        IPC 서버 초기화

        Args:
            simulation_dir: 시뮬레이션 데이터 디렉토리
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")
        # Double-consume 방지: poll 시 명령을 여기로 이동시켜 다른 폴링이 못 보게 함
        self.processing_dir = os.path.join(self.commands_dir, _PROCESSING_SUBDIR)

        # 디렉토리 존재 확인
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
        os.makedirs(self.processing_dir, exist_ok=True)

        # 환경 상태
        self._running = False

    def start(self):
        """서버를 실행 상태로 표시"""
        self._running = True
        self.update_status("alive")

    def stop(self):
        """서버를 중지 상태로 표시"""
        self._running = False
        self.update_status("stopped")

    def update_status(
        self,
        status: str,
        twitter_available: Optional[bool] = None,
        reddit_available: Optional[bool] = None,
    ) -> None:
        """
        환경 상태 파일 원자적 업데이트.

        Args:
            status: "running", "alive", "stopped" 등
            twitter_available: 양 플랫폼 시뮬레이션 시 Twitter 가용 여부
            reddit_available: 양 플랫폼 시뮬레이션 시 Reddit 가용 여부
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        data: Dict[str, Any] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }
        if twitter_available is not None:
            data["twitter_available"] = twitter_available
        if reddit_available is not None:
            data["reddit_available"] = reddit_available
        _atomic_write_json(status_file, data)

    def get_env_status(self) -> Dict[str, Any]:
        """
        env_status.json 의 전체 필드 반환 (없으면 기본값).
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        if not os.path.exists(status_file):
            return {"status": "stopped", "timestamp": None}
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"status": "stopped", "timestamp": None}

    def poll_commands(self) -> Optional[IPCCommand]:
        """
        명령 디렉토리 폴링, 첫 번째 대기 중인 명령 반환.
        반환 직전에 명령 파일을 processing/ 으로 원자적 이동시켜 double-consume 방지.
        """
        if not os.path.exists(self.commands_dir):
            return None

        # 시간순으로 정렬하여 명령 파일 가져오기 (processing/ 서브디렉토리는 제외)
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if not filename.endswith('.json'):
                continue
            filepath = os.path.join(self.commands_dir, filename)
            if not os.path.isfile(filepath):
                continue
            command_files.append((filepath, filename, os.path.getmtime(filepath)))

        command_files.sort(key=lambda x: x[2])

        for filepath, filename, _ in command_files:
            # 소유권 이전: commands/{id}.json → commands/.processing/{id}.json
            # 다른 poll 호출이 이 명령을 다시 보지 못하게 함
            processing_path = os.path.join(self.processing_dir, filename)
            try:
                os.replace(filepath, processing_path)
            except OSError as e:
                # 이미 다른 poller가 가져감 (race) — 스킵
                logger.debug(f"poll race: {filepath} 이미 이동됨 ({e})")
                continue

            try:
                with open(processing_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return IPCCommand.from_dict(data)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"명령 파일 읽기 실패: {processing_path}, {e}")
                # 파싱 실패한 파일은 그대로 processing/ 에 남겨두어 재시도 X (orphan)
                continue

        return None

    def send_response(self, response: IPCResponse):
        """응답 원자적 전송 + processing/ 의 명령 파일 정리"""
        response_file = os.path.join(self.responses_dir, f"{response.command_id}.json")
        _atomic_write_json(response_file, response.to_dict())

        # 처리 완료된 명령 파일 삭제 (processing/ → commands/ 순으로 확인)
        for cmd_path in (
            os.path.join(self.processing_dir, f"{response.command_id}.json"),
            os.path.join(self.commands_dir, f"{response.command_id}.json"),
        ):
            try:
                os.remove(cmd_path)
                break
            except OSError:
                continue

    def send_success(self, command_id: str, result: Dict[str, Any]):
        """성공 응답 전송"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result
        ))

    def send_error(self, command_id: str, error: str):
        """오류 응답 전송"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error
        ))
