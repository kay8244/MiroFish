"""
Pipeline Orchestrator

MiroFish 5단계 워크플로우(seed 업로드 → 그래프 → 에이전트 → 시뮬레이션 → 보고서)를
웹에서 사람 개입 없이 end-to-end 완주시키는 오케스트레이터.

설계 원칙:
- 기존 서비스(graph_builder, oasis_profile_generator, simulation_runner, report_agent)
  내부 구현은 수정하지 않는다. 서비스 호출 경계에서만 동작한다.
- 단계별 상태는 SQLite에 영속화한다(stdlib sqlite3 + raw SQL).
- 단계별 산출물은 임시 디렉토리에 쓰고 성공 시 atomic_move_dir로 최종 디렉토리에
  이관한다 (같은 파일시스템 보장).
- 재시도는 step-level에 적용한다 (@retry_with_backoff, max_retries=3, exp backoff).
  LLM 호출별 내부 재시도는 기존 llm_client 동작 그대로.
- 각 단계에 wall-clock 상한을 둔다 (seed_upload=2min, graph=10min, agents=10min,
  simulation=30min, report=20min). 초과 시 재시도 카운트와 무관하게 fail.
- Zep 부수 효과 격리: 모든 Zep 쓰기에 group_id="run_<run_id>" 네임스페이스 사용.
  Resume 시 해당 group을 purge한 뒤 전체 재실행 (delete_group도 3회 재시도).
  purge 3회 실패 시 run은 failed_cleanup 상태로 마킹되어 resume 차단.

데이터 플로우:
  POST /api/pipeline/run
    └─> PipelineOrchestrator.start_run()
        └─> For each step in [1..5]:
              ├─ idempotency check
              ├─ allocate tmp dir (uploads/runs/{rid}/_tmp/{step}-{uuid}/)
              ├─ @retry_with_backoff + wall_clock
              ├─ call existing service (UNMODIFIED)
              ├─ on success: atomic_move_dir(tmp → uploads/runs/{rid}/{step}/)
              └─ persist step record to SQLite
        └─> update manifest, return run_id

상세 디자인은 ~/.gstack/projects/03_mirofish/keonsoopark-master-design-20260418-201747.md
참조 (Architecture Addendum 섹션).
"""

import os
import uuid
import json
import time
import sqlite3
import hashlib
import threading
import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from ..config import Config
from ..utils.logger import get_logger
from ..utils.retry import retry_with_backoff
from ..utils.atomic_fs import atomic_move_dir, ensure_same_filesystem, CrossDeviceError

logger = get_logger('mirofish.pipeline')

# LLM 호출 카운팅용 contextvar
# 각 단계 시작 전 reset, 종료 시 manifest의 steps[i].llm_calls에 기록
llm_call_counter: contextvars.ContextVar[int] = contextvars.ContextVar(
    'pipeline_llm_call_counter', default=0
)


# ─────────────────────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────────────────────

STEP_NAMES = ['seed_upload', 'graph', 'agents', 'simulation', 'report']

WALL_CLOCK_SECONDS = {
    'seed_upload': 2 * 60,
    'graph': 10 * 60,
    'agents': 10 * 60,
    'simulation': 30 * 60,
    'report': 20 * 60,
}

RUN_STATUS_PENDING = 'pending'
RUN_STATUS_RUNNING = 'running'
RUN_STATUS_FAILED = 'failed'
RUN_STATUS_COMPLETED = 'completed'
RUN_STATUS_FAILED_CLEANUP = 'failed_cleanup'

STEP_STATUS_PENDING = 'pending'
STEP_STATUS_RUNNING = 'running'
STEP_STATUS_FAILED = 'failed'
STEP_STATUS_COMPLETED = 'completed'


# ─────────────────────────────────────────────────────────────────────
# 경로 헬퍼
# ─────────────────────────────────────────────────────────────────────

def _backend_root() -> Path:
    """backend/ 루트 경로"""
    return Path(__file__).resolve().parents[2]


def _runs_base_dir() -> Path:
    """runs 산출물 루트: backend/uploads/runs/"""
    p = _backend_root() / 'uploads' / 'runs'
    p.mkdir(parents=True, exist_ok=True)
    return p


def _run_dir(run_id: str) -> Path:
    return _runs_base_dir() / run_id


def _step_final_dir(run_id: str, step_name: str) -> Path:
    # 단계 순서 prefix로 정렬 가능하게
    idx = STEP_NAMES.index(step_name) + 1
    return _run_dir(run_id) / f'{idx}-{step_name}'


def _step_tmp_dir(run_id: str, step_name: str) -> Path:
    """임시 디렉토리: 반드시 최종 디렉토리와 같은 파일시스템 내"""
    idx = STEP_NAMES.index(step_name) + 1
    return _run_dir(run_id) / '_tmp' / f'{idx}-{step_name}-{uuid.uuid4().hex[:8]}'


def _manifest_path(run_id: str) -> Path:
    return _run_dir(run_id) / 'manifest.json'


def _db_path() -> Path:
    return _backend_root() / 'pipeline.sqlite3'


# ─────────────────────────────────────────────────────────────────────
# 데이터클래스
# ─────────────────────────────────────────────────────────────────────

@dataclass
class StepRecord:
    name: str
    status: str
    duration_s: float = 0.0
    llm_calls: int = 0
    retry_count: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_summary: Optional[str] = None


@dataclass
class ErrorPayload:
    step: str
    retry_count: int
    retry_exhausted: bool
    wall_clock_exceeded: bool
    summary: str
    manifest_url: str


@dataclass
class RunStatus:
    run_id: str
    status: str
    current_step: Optional[str]
    error: Optional[dict]
    resumable_from: Optional[str]
    steps: list


# ─────────────────────────────────────────────────────────────────────
# DB 스키마 + 접근
# ─────────────────────────────────────────────────────────────────────

_db_lock = threading.Lock()


@contextmanager
def _db_conn():
    conn = sqlite3.connect(str(_db_path()), isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """
    SQLite 스키마 초기화. 앱 부팅 시 1회 호출되며 멱등하다
    (CREATE TABLE IF NOT EXISTS). 재호출 시 예외 없음.
    """
    with _db_lock, _db_conn() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                zep_group_id TEXT NOT NULL,
                assumptions_version TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                manifest_json TEXT
            );

            CREATE TABLE IF NOT EXISTS pipeline_steps (
                run_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                duration_s REAL DEFAULT 0,
                llm_calls INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                artifact_path TEXT,
                error_summary TEXT,
                PRIMARY KEY (run_id, step_name),
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_steps_status
                ON pipeline_steps(run_id, status);
        ''')
        logger.info('pipeline SQLite 스키마 초기화 완료')


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


# ─────────────────────────────────────────────────────────────────────
# Step adapter 시그니처
# ─────────────────────────────────────────────────────────────────────

@dataclass
class StepContext:
    """단계 실행에 주입되는 컨텍스트. 기존 서비스는 수정하지 않고
    오케스트레이터가 이 컨텍스트를 기반으로 서비스 호출 방법을 결정한다."""
    run_id: str
    step_name: str
    zep_group_id: str
    seed_dir: Path          # 1단계 이후 단계가 읽는 seed 디렉토리
    tmp_dir: Path           # 현재 단계가 쓸 임시 디렉토리
    prev_step_dir: Optional[Path]  # 직전 단계의 최종 디렉토리 (입력)
    assumptions_version: str
    config: dict            # 사용자 입력 추가 설정


StepFn = Callable[[StepContext], dict]
"""단계 구현 함수 시그니처. 리턴값은 manifest에 합쳐질 dict(step_meta)."""


# 단계 구현은 _step_adapters.py로 분리된다 (다음 커밋).
# 여기서는 registry 인터페이스만 정의하고 외부에서 주입받는다.
_STEP_REGISTRY: dict[str, StepFn] = {}


def register_step(name: str, fn: StepFn) -> None:
    if name not in STEP_NAMES:
        raise ValueError(f'unknown step: {name}')
    _STEP_REGISTRY[name] = fn


def _get_step_fn(name: str) -> StepFn:
    if name not in _STEP_REGISTRY:
        raise RuntimeError(
            f"step '{name}' is not registered. "
            f"서비스 어댑터가 등록되지 않음 (다음 커밋에서 연결)."
        )
    return _STEP_REGISTRY[name]


# ─────────────────────────────────────────────────────────────────────
# 오케스트레이터
# ─────────────────────────────────────────────────────────────────────

class PipelineOrchestrator:
    """파이프라인 실행 오케스트레이터.

    인스턴스 상태를 갖지 않으며 모든 상태는 SQLite + 파일시스템에 영속화된다.
    동시 호출은 SQLite UNIQUE 제약으로 방어되지만, 단일 빌더 MVP에서는 한
    번에 하나의 run만 돌린다고 가정한다.
    """

    def start_run(
        self,
        seed_files: list[Path],
        assumptions_version: str,
        extra_config: Optional[dict] = None,
    ) -> str:
        """새 run을 생성하고 1~5단계를 백그라운드 thread에서 순차 실행한다.

        API 엔드포인트 타임아웃(기본 10초)과 무관하게 run_id를 즉시 반환하기
        위해 seed 복사 + DB 선등록만 동기로 수행하고, `_run_loop`는 daemon
        thread에서 실행한다. 호출자는 run_id를 받아 `GET /api/pipeline/status/<id>`
        로 진행 상황을 폴링한다.

        seed_upload 단계는 start_run 내에서 파일 복사 + DB completed 선등록으로
        이미 완료된 것으로 간주한다 (어댑터 불필요). `_run_loop`는 idempotency
        체크로 seed_upload를 스킵하고 graph 단계부터 실행한다.

        한 단계라도 실패하면 run은 failed 상태로 종료되며, resume은 `resume_run`
        으로 호출한다. Zep group_id(실제 graph_id)는 'run_<run_id>'로 고정.

        Returns:
            run_id (uuid hex) — 즉시 반환
        """
        run_id = uuid.uuid4().hex
        zep_group_id = f'run_{run_id}'
        now = _now_iso()

        with _db_conn() as conn:
            conn.execute(
                'INSERT INTO pipeline_runs (run_id, status, zep_group_id, '
                'assumptions_version, created_at, updated_at, manifest_json) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (run_id, RUN_STATUS_PENDING, zep_group_id, assumptions_version,
                 now, now, json.dumps({})),
            )
        logger.info(f'run 시작: {run_id} (zep_group={zep_group_id})')

        # seed 파일을 1단계 디렉토리에 복사 (run directory에서 고정 경로 확보)
        seed_final = _step_final_dir(run_id, 'seed_upload')
        seed_final.mkdir(parents=True, exist_ok=True)
        _copy_seed_files(seed_files, seed_final)

        # MC-5: seed_upload 단계를 완료 상태로 DB에 선등록.
        # _run_loop의 idempotency 스킵이 작동하려면 완료 레코드가 필요함.
        # 동기 경로이므로 seed 파일 복사 직후 등록해도 race 없음.
        seed_completed_at = _now_iso()
        seed_file_count = sum(1 for _ in seed_final.iterdir() if _.is_file())
        with _db_conn() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO pipeline_steps '
                '(run_id, step_name, status, idempotency_key, started_at, '
                'completed_at, duration_s, llm_calls, retry_count, artifact_path) '
                'VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?)',
                (run_id, 'seed_upload', STEP_STATUS_COMPLETED,
                 f'{run_id}:seed_upload', now, seed_completed_at,
                 str(seed_final)),
            )
        logger.info(
            f'{run_id}/seed_upload 완료 선등록 '
            f'(files={seed_file_count}, dir={seed_final})'
        )

        # MC-4: `_run_loop`를 daemon thread에서 실행하고 run_id를 즉시 반환.
        # daemon=True로 지정하여 앱 종료 시 thread가 process를 붙잡지 않도록 함.
        # MVP 단일 빌더 가정 하에서 thread 추적은 불필요 (상태는 DB에 영속화됨).
        thread = threading.Thread(
            target=self._run_loop,
            kwargs={
                'run_id': run_id,
                'zep_group_id': zep_group_id,
                'assumptions_version': assumptions_version,
                'extra_config': extra_config or {},
                'start_from': 'seed_upload',
            },
            name=f'pipeline-run-{run_id[:8]}',
            daemon=True,
        )
        thread.start()
        logger.info(f'run 백그라운드 thread 시작: {thread.name}')
        return run_id

    def resume_run(self, run_id: str) -> None:
        """실패한 run을 재개한다. 재개 전 Zep group을 purge하여 외부 상태
        오염을 제거한다. purge 3회 실패 시 run은 failed_cleanup 상태로
        마킹되어 이후 resume이 차단된다.
        """
        with _db_conn() as conn:
            row = conn.execute(
                'SELECT status, zep_group_id, assumptions_version FROM pipeline_runs WHERE run_id = ?',
                (run_id,),
            ).fetchone()
        if row is None:
            raise RunNotFound(run_id)
        if row['status'] == RUN_STATUS_COMPLETED:
            raise RunAlreadyCompleted(run_id)
        if row['status'] == RUN_STATUS_FAILED_CLEANUP:
            raise RunCleanupFailed(run_id)

        zep_group_id = row['zep_group_id']
        assumptions_version = row['assumptions_version'] or ''

        # Zep purge (3회 재시도)
        try:
            self._purge_zep_group_with_retry(zep_group_id)
        except Exception as e:
            logger.error(f'resume 실패: Zep purge 3회 재시도 불가. run={run_id}, {e}')
            self._mark_run(run_id, RUN_STATUS_FAILED_CLEANUP)
            raise ZepPurgeFailed(run_id, str(e)) from e

        # purge 성공: 모든 step 레코드를 삭제해 첫 단계부터 다시 실행
        # (idempotency 완전 초기화 = 깨끗한 group 위에서 재시작)
        with _db_conn() as conn:
            conn.execute(
                'DELETE FROM pipeline_steps WHERE run_id = ?', (run_id,)
            )
            conn.execute(
                'UPDATE pipeline_runs SET status = ?, updated_at = ? WHERE run_id = ?',
                (RUN_STATUS_PENDING, _now_iso(), run_id),
            )

        # 산출물 디렉토리 정리 (seed_upload는 보존, 나머지 4단계 제거)
        for step in STEP_NAMES[1:]:
            d = _step_final_dir(run_id, step)
            if d.exists():
                import shutil
                shutil.rmtree(d)
        tmp = _run_dir(run_id) / '_tmp'
        if tmp.exists():
            import shutil
            shutil.rmtree(tmp)

        self._run_loop(
            run_id=run_id,
            zep_group_id=zep_group_id,
            assumptions_version=assumptions_version,
            extra_config={},
            start_from='graph',  # seed는 보존했으므로 2단계부터
        )

    def get_status(self, run_id: str) -> dict:
        """A3 API 에러 계약 스키마 형태로 상태 반환"""
        with _db_conn() as conn:
            run_row = conn.execute(
                'SELECT status FROM pipeline_runs WHERE run_id = ?', (run_id,)
            ).fetchone()
            if run_row is None:
                raise RunNotFound(run_id)
            step_rows = conn.execute(
                'SELECT step_name, status, duration_s, llm_calls, retry_count, '
                'error_summary FROM pipeline_steps WHERE run_id = ? '
                'ORDER BY step_name',
                (run_id,),
            ).fetchall()

        # 순서를 STEP_NAMES 기준으로 정렬
        by_name = {r['step_name']: r for r in step_rows}
        steps = []
        current_step = None
        error_payload = None
        resumable_from = None

        for name in STEP_NAMES:
            r = by_name.get(name)
            if r is None:
                steps.append({
                    'name': name,
                    'status': STEP_STATUS_PENDING,
                    'duration_s': 0,
                    'llm_calls': 0,
                    'retry_count': 0,
                })
            else:
                steps.append({
                    'name': r['step_name'],
                    'status': r['status'],
                    'duration_s': r['duration_s'],
                    'llm_calls': r['llm_calls'],
                    'retry_count': r['retry_count'],
                })
                if r['status'] == STEP_STATUS_RUNNING:
                    current_step = name
                if r['status'] == STEP_STATUS_FAILED:
                    current_step = name
                    error_payload = {
                        'step': name,
                        'retry_count': r['retry_count'],
                        'retry_exhausted': r['retry_count'] >= 3,
                        'wall_clock_exceeded': False,  # 원인 세분화는 Phase 2
                        'summary': r['error_summary'] or '',
                        'manifest_url': f'/api/pipeline/manifest/{run_id}',
                    }
                    resumable_from = name

        return {
            'run_id': run_id,
            'status': run_row['status'],
            'current_step': current_step,
            'error': error_payload,
            'resumable_from': resumable_from,
            'steps': steps,
        }

    def get_manifest(self, run_id: str) -> dict:
        mpath = _manifest_path(run_id)
        if not mpath.exists():
            raise RunNotFound(run_id)
        return json.loads(mpath.read_text(encoding='utf-8'))

    # ─── 내부 ───────────────────────────────────────────────────────

    def _run_loop(
        self,
        run_id: str,
        zep_group_id: str,
        assumptions_version: str,
        extra_config: dict,
        start_from: str,
    ) -> None:
        self._mark_run(run_id, RUN_STATUS_RUNNING)
        start_idx = STEP_NAMES.index(start_from)
        seed_dir = _step_final_dir(run_id, 'seed_upload')

        try:
            for i in range(start_idx, len(STEP_NAMES)):
                step = STEP_NAMES[i]
                # idempotency: 이미 완료된 단계는 스킵
                if self._step_completed(run_id, step):
                    logger.info(f'{run_id}/{step} 이미 완료, 스킵')
                    continue

                prev = _step_final_dir(run_id, STEP_NAMES[i - 1]) if i > 0 else None
                tmp = _step_tmp_dir(run_id, step)
                tmp.parent.mkdir(parents=True, exist_ok=True)

                # 같은 파일시스템 확인 (uploads/runs/.. 하위에 배치하므로 항상 OK여야 함)
                if not ensure_same_filesystem(tmp.parent, _step_final_dir(run_id, step).parent):
                    raise AssertionError(
                        'tmp_dir와 final_dir가 다른 파일시스템. '
                        '반드시 같은 mount point 하위에 배치되어야 함.'
                    )

                ctx = StepContext(
                    run_id=run_id,
                    step_name=step,
                    zep_group_id=zep_group_id,
                    seed_dir=seed_dir,
                    tmp_dir=tmp,
                    prev_step_dir=prev,
                    assumptions_version=assumptions_version,
                    config=extra_config,
                )
                self._execute_step(ctx)

            self._mark_run(run_id, RUN_STATUS_COMPLETED)
            self._write_manifest(run_id)
            logger.info(f'run 완료: {run_id}')

        except StepFailed as e:
            logger.warning(f'run 실패: {run_id}, 단계={e.step}, 원인={e.summary}')
            self._mark_run(run_id, RUN_STATUS_FAILED)
            self._write_manifest(run_id)
            # 예외를 호출자에게 돌려주지 않는다 (동기 호출에서 HTTP 에러 대신
            # status=failed로 확인 가능하도록)

    def _execute_step(self, ctx: StepContext) -> None:
        """단계 실행: retry + wall-clock + idempotency + atomic move"""
        idempotency_key = f'{ctx.run_id}:{ctx.step_name}'
        started_at = _now_iso()
        t0 = time.time()

        # 단계 레코드 선점
        with _db_conn() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO pipeline_steps '
                '(run_id, step_name, status, idempotency_key, started_at, retry_count) '
                'VALUES (?, ?, ?, ?, ?, 0)',
                (ctx.run_id, ctx.step_name, STEP_STATUS_RUNNING,
                 idempotency_key, started_at),
            )

        step_fn = _get_step_fn(ctx.step_name)
        wall = WALL_CLOCK_SECONDS[ctx.step_name]

        # LLM 카운터 초기화
        token = llm_call_counter.set(0)

        retry_count_holder = {'n': 0}

        def _on_retry(exc: Exception, retry_no: int) -> None:
            retry_count_holder['n'] = retry_no
            logger.warning(
                f'{ctx.run_id}/{ctx.step_name} retry {retry_no}: {exc}'
            )

        @retry_with_backoff(
            max_retries=3,
            initial_delay=2.0,
            max_delay=30.0,
            backoff_factor=2.0,
            jitter=True,
            exceptions=(Exception,),
            on_retry=_on_retry,
        )
        def _run_once() -> dict:
            # wall-clock 검사는 각 호출 후 외부 래퍼에서 수행
            if time.time() - t0 > wall:
                raise WallClockExceeded(ctx.step_name, wall)
            return step_fn(ctx)

        meta: dict = {}
        error: Optional[Exception] = None
        try:
            meta = _run_once()
        except Exception as e:
            error = e

        duration = time.time() - t0
        llm_calls = llm_call_counter.get()
        llm_call_counter.reset(token)

        if error is not None:
            summary = _summarize_exception(error)
            with _db_conn() as conn:
                conn.execute(
                    'UPDATE pipeline_steps SET status=?, completed_at=?, '
                    'duration_s=?, llm_calls=?, retry_count=?, error_summary=? '
                    'WHERE run_id=? AND step_name=?',
                    (STEP_STATUS_FAILED, _now_iso(), duration, llm_calls,
                     retry_count_holder['n'], summary, ctx.run_id, ctx.step_name),
                )
            raise StepFailed(ctx.step_name, summary) from error

        # 성공: atomic move tmp → final
        final_dir = _step_final_dir(ctx.run_id, ctx.step_name)
        try:
            atomic_move_dir(ctx.tmp_dir, final_dir, overwrite=True)
        except CrossDeviceError as e:
            # 설계상 절대 발생하지 않아야 하므로 step 실패로 처리
            with _db_conn() as conn:
                conn.execute(
                    'UPDATE pipeline_steps SET status=?, completed_at=?, '
                    'duration_s=?, llm_calls=?, retry_count=?, error_summary=? '
                    'WHERE run_id=? AND step_name=?',
                    (STEP_STATUS_FAILED, _now_iso(), duration, llm_calls,
                     retry_count_holder['n'], f'CrossDeviceError: {e}',
                     ctx.run_id, ctx.step_name),
                )
            raise StepFailed(ctx.step_name, f'atomic move 실패: {e}') from e

        with _db_conn() as conn:
            conn.execute(
                'UPDATE pipeline_steps SET status=?, completed_at=?, '
                'duration_s=?, llm_calls=?, retry_count=?, artifact_path=? '
                'WHERE run_id=? AND step_name=?',
                (STEP_STATUS_COMPLETED, _now_iso(), duration, llm_calls,
                 retry_count_holder['n'], str(final_dir),
                 ctx.run_id, ctx.step_name),
            )
        logger.info(
            f'{ctx.run_id}/{ctx.step_name} 완료 '
            f'(duration={duration:.1f}s, llm_calls={llm_calls})'
        )

    def _step_completed(self, run_id: str, step_name: str) -> bool:
        with _db_conn() as conn:
            row = conn.execute(
                'SELECT status FROM pipeline_steps WHERE run_id=? AND step_name=?',
                (run_id, step_name),
            ).fetchone()
        return row is not None and row['status'] == STEP_STATUS_COMPLETED

    def _mark_run(self, run_id: str, status: str) -> None:
        with _db_conn() as conn:
            conn.execute(
                'UPDATE pipeline_runs SET status=?, updated_at=? WHERE run_id=?',
                (status, _now_iso(), run_id),
            )

    def _purge_zep_group_with_retry(self, zep_group_id: str) -> None:
        """Zep graph 삭제. 3회 재시도 실패 시 예외.

        `zep_group_id`는 오케스트레이터 내부 네이밍이지만 실제로는 Zep graph_id로
        사용된다 (graph_builder.py + zep_graph_memory_updater.py 와 동일 체계).
        Zep Cloud SDK(zep_cloud.client.Zep)의 공식 API는 `client.graph.delete(graph_id=...)`.
        `graph_builder.py:499` 의 delete 호출과 동일 시그니처.

        Graph가 존재하지 않는 경우(404 등)는 이미 purge된 것으로 간주하고 성공 처리.
        """
        from zep_cloud.errors import NotFoundError  # type: ignore

        @retry_with_backoff(max_retries=3, initial_delay=2.0, backoff_factor=2.0)
        def _purge():
            from ..utils.zep_client import create_zep_client
            client = create_zep_client()
            try:
                client.graph.delete(graph_id=zep_group_id)
                logger.info(f'Zep graph 삭제 완료: graph_id={zep_group_id}')
            except NotFoundError:
                # 해당 graph가 원래부터 없었거나 이전 시도에서 이미 삭제됨 → 성공으로 간주
                logger.info(
                    f'Zep graph 존재하지 않음(이미 purge된 것으로 간주): '
                    f'graph_id={zep_group_id}'
                )
        _purge()

    def _write_manifest(self, run_id: str) -> None:
        with _db_conn() as conn:
            run_row = conn.execute(
                'SELECT status, zep_group_id, assumptions_version, created_at '
                'FROM pipeline_runs WHERE run_id=?', (run_id,)
            ).fetchone()
            step_rows = conn.execute(
                'SELECT step_name, status, duration_s, llm_calls, retry_count, '
                'started_at, completed_at, error_summary '
                'FROM pipeline_steps WHERE run_id=?',
                (run_id,),
            ).fetchall()

        seed_dir = _step_final_dir(run_id, 'seed_upload')
        seed_hashes = _hash_seed_files(seed_dir) if seed_dir.exists() else {}

        manifest = {
            'run_id': run_id,
            'status': run_row['status'],
            'zep_group_id': run_row['zep_group_id'],
            'assumptions_version': run_row['assumptions_version'],
            'created_at': run_row['created_at'],
            'completed_at': _now_iso(),
            'operator': os.environ.get('USER', 'unknown'),
            'llm_model': os.environ.get('LLM_MODEL_NAME', 'unknown'),
            'seed_files': seed_hashes,
            'urls': [],  # 다음 커밋에서 URL 수집 시점 스냅샷 기록
            'prompt_template_version': 'ai_server_si_wafer_v1',
            'steps': [
                {
                    'name': r['step_name'],
                    'status': r['status'],
                    'duration_s': r['duration_s'],
                    'llm_calls': r['llm_calls'],
                    'retry_count': r['retry_count'],
                    'started_at': r['started_at'],
                    'completed_at': r['completed_at'],
                    'error_summary': r['error_summary'],
                }
                for r in step_rows
            ],
        }
        _manifest_path(run_id).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )


# ─────────────────────────────────────────────────────────────────────
# 예외
# ─────────────────────────────────────────────────────────────────────

class PipelineError(Exception):
    pass


class RunNotFound(PipelineError):
    def __init__(self, run_id: str):
        super().__init__(f'run not found: {run_id}')
        self.run_id = run_id


class RunAlreadyCompleted(PipelineError):
    def __init__(self, run_id: str):
        super().__init__(f'run already completed: {run_id}')
        self.run_id = run_id


class RunCleanupFailed(PipelineError):
    def __init__(self, run_id: str):
        super().__init__(
            f'run is in failed_cleanup state (Zep purge 3회 실패). '
            f'새 run을 시작해야 함. run_id={run_id}'
        )
        self.run_id = run_id


class ZepPurgeFailed(PipelineError):
    def __init__(self, run_id: str, reason: str):
        super().__init__(f'Zep purge 실패 (3회 재시도 소진): run={run_id}, {reason}')
        self.run_id = run_id


class StepFailed(PipelineError):
    def __init__(self, step: str, summary: str):
        super().__init__(f'step {step} failed: {summary}')
        self.step = step
        self.summary = summary


class WallClockExceeded(PipelineError):
    def __init__(self, step: str, limit: int):
        super().__init__(f'wall-clock exceeded for step {step}: limit={limit}s')
        self.step = step
        self.limit = limit


# ─────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────

def _copy_seed_files(seed_files: list[Path], dst_dir: Path) -> None:
    import shutil
    for f in seed_files:
        p = Path(f)
        if not p.exists():
            raise FileNotFoundError(f'seed 파일 없음: {p}')
        shutil.copy2(p, dst_dir / p.name)


def _hash_seed_files(seed_dir: Path) -> dict:
    result = {}
    for f in sorted(seed_dir.iterdir()):
        if f.is_file():
            h = hashlib.sha256()
            with f.open('rb') as fp:
                for chunk in iter(lambda: fp.read(65536), b''):
                    h.update(chunk)
            result[f.name] = h.hexdigest()
    return result


def _summarize_exception(e: Exception) -> str:
    """에러 한 줄 요약 (UI 표면용)"""
    msg = str(e) or e.__class__.__name__
    if len(msg) > 200:
        msg = msg[:197] + '...'
    return f'{e.__class__.__name__}: {msg}'
