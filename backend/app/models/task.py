"""
태스크 상태 관리
장시간 실행 작업（예: 그래프 구축）추적에 사용
"""

import uuid
import threading
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from ..utils.logger import get_logger

_logger = get_logger('mirofish.task_manager')

# Lazy cleanup: N번 create마다 1번 오래된 태스크 정리 (부하 무시 가능)
_CLEANUP_EVERY_N_CREATES = 100
# PROCESSING 상태로 N분 이상 멈춰있으면 고아 태스크로 간주 → FAILED 전환
_STALE_PROCESSING_MINUTES = 60
# COMPLETED/FAILED 태스크는 N시간 뒤 삭제
_COMPLETED_MAX_AGE_HOURS = 24


class TaskStatus(str, Enum):
    """태스크 상태 열거형"""
    PENDING = "pending"          # 대기 중
    PROCESSING = "processing"    # 처리 중
    COMPLETED = "completed"      # 완료됨
    FAILED = "failed"            # 실패


@dataclass
class Task:
    """태스크 데이터 클래스"""
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: int = 0              # 전체 진행률 0-100
    message: str = ""              # 상태 메시지
    result: Optional[Dict] = None  # 태스크 결과
    error: Optional[str] = None    # 오류 정보
    metadata: Dict = field(default_factory=dict)  # 추가 메타데이터
    progress_detail: Dict = field(default_factory=dict)  # 상세 진행 정보

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": self.progress,
            "message": self.message,
            "progress_detail": self.progress_detail,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class TaskManager:
    """
    태스크 관리자
    스레드 안전한 태스크 상태 관리
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """싱글톤 패턴"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: Dict[str, Task] = {}
                    cls._instance._task_lock = threading.Lock()
                    cls._instance._create_count = 0
        return cls._instance

    def create_task(self, task_type: str, metadata: Optional[Dict] = None) -> str:
        """
        새 태스크 생성

        Args:
            task_type: 태스크 유형
            metadata: 추가 메타데이터

        Returns:
            태스크 ID
        """
        task_id = str(uuid.uuid4())
        now = datetime.now()

        task = Task(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )

        with self._task_lock:
            self._tasks[task_id] = task
            self._create_count += 1
            should_cleanup = self._create_count % _CLEANUP_EVERY_N_CREATES == 0

        if should_cleanup:
            self._run_lazy_cleanup()

        return task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        """태스크 조회"""
        with self._task_lock:
            return self._tasks.get(task_id)

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
        progress_detail: Optional[Dict] = None
    ):
        """
        태스크 상태 업데이트

        Args:
            task_id: 태스크 ID
            status: 새 상태
            progress: 진행률
            message: 메시지
            result: 결과
            error: 오류 정보
            progress_detail: 상세 진행 정보
        """
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.updated_at = datetime.now()
                if status is not None:
                    task.status = status
                if progress is not None:
                    task.progress = progress
                if message is not None:
                    task.message = message
                if result is not None:
                    task.result = result
                if error is not None:
                    task.error = error
                if progress_detail is not None:
                    task.progress_detail = progress_detail

    def complete_task(self, task_id: str, result: Dict):
        """태스크 완료 표시"""
        self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="태스크 완료",
            result=result
        )

    def fail_task(self, task_id: str, error: str):
        """태스크 실패 표시"""
        self.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message="태스크 실패",
            error=error
        )

    def list_tasks(self, task_type: Optional[str] = None) -> list:
        """태스크 목록 조회"""
        with self._task_lock:
            tasks = list(self._tasks.values())
            if task_type:
                tasks = [t for t in tasks if t.task_type == task_type]
            return [t.to_dict() for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)]

    def cleanup_old_tasks(self, max_age_hours: int = _COMPLETED_MAX_AGE_HOURS):
        """오래된 COMPLETED/FAILED 태스크 삭제"""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        with self._task_lock:
            old_ids = [
                tid for tid, task in self._tasks.items()
                if task.created_at < cutoff and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
            ]
            for tid in old_ids:
                del self._tasks[tid]
        if old_ids:
            _logger.info(f"오래된 태스크 정리: {len(old_ids)}건 삭제")

    def reap_stale_processing(self, stale_minutes: int = _STALE_PROCESSING_MINUTES):
        """updated_at 이 stale_minutes 이상 지난 PROCESSING 태스크를 FAILED로 전환 (고아 태스크)"""
        cutoff = datetime.now() - timedelta(minutes=stale_minutes)
        stale_ids = []

        with self._task_lock:
            for tid, task in self._tasks.items():
                if task.status == TaskStatus.PROCESSING and task.updated_at < cutoff:
                    task.status = TaskStatus.FAILED
                    task.error = f"stale: {stale_minutes}분 이상 업데이트 없음 (프로세스 크래시 추정)"
                    task.message = "고아 태스크로 판정됨"
                    task.updated_at = datetime.now()
                    stale_ids.append(tid)

        if stale_ids:
            _logger.warning(f"고아 PROCESSING 태스크 FAILED 전환: {len(stale_ids)}건")

    def _run_lazy_cleanup(self):
        """create_task 에서 주기적으로 호출되는 백그라운드 정리"""
        try:
            self.reap_stale_processing()
            self.cleanup_old_tasks()
        except Exception as e:
            _logger.warning(f"lazy cleanup 실패 (무시): {e}")

