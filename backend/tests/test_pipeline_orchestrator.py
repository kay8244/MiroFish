"""
PipelineOrchestrator 단위 테스트 (`app/services/pipeline_orchestrator.py`).

검증 단위:
- 헬퍼: `_copy_seed_files`, `_hash_seed_files`, `_summarize_exception`, `_now_iso`
- Step registry: `register_step`, `_get_step_fn`
- 예외 클래스: RunNotFound / RunAlreadyCompleted / RunCleanupFailed / ZepPurgeFailed
                / StepFailed / WallClockExceeded
- DB: `init_db` (멱등)
- Orchestrator: start_run / get_status / get_manifest / _execute_step / _run_loop
                / resume_run (purge mock + step 삭제)

격리: `_db_path` 와 `_backend_root` 를 monkeypatch 해 tmp_path 아래로 SQLite + runs/ 리다이렉트.
threading.Thread 은 인라인 (start_run 이 _run_loop 즉시 실행).
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import pipeline_orchestrator as po
from app.services.pipeline_orchestrator import (
    PipelineOrchestrator,
    RunAlreadyCompleted,
    RunCleanupFailed,
    RunNotFound,
    StepFailed,
    WallClockExceeded,
    ZepPurgeFailed,
    _STEP_REGISTRY,
    _copy_seed_files,
    _get_step_fn,
    _hash_seed_files,
    _summarize_exception,
    init_db,
    register_step,
)


# ============================================================================
# Fake Thread (start_run 이 thread.name 로깅 → 속성 필수)
# ============================================================================

class _NoopThread:
    def __init__(self, target=None, kwargs=None, name="fake", **kw):
        self.name = name
    def start(self):
        pass


class _InlineThread:
    """target 을 즉시 인라인 실행."""
    def __init__(self, target=None, kwargs=None, name="fake", **kw):
        self.name = name
        self._target = target
        self._kwargs = kwargs or {}
    def start(self):
        if self._target is not None:
            self._target(**self._kwargs)


# ============================================================================
# Fixtures: SQLite + filesystem 격리
# ============================================================================

@pytest.fixture
def isolated_pipeline(tmp_path, monkeypatch):
    """SQLite + runs 디렉토리를 tmp_path 로 리다이렉트 + step registry 격리."""
    # 1) DB
    db_file = tmp_path / "test_pipeline.sqlite3"
    monkeypatch.setattr(po, "_db_path", lambda: db_file)

    # 2) backend_root → tmp_path (runs/, manifest/ 등 모두 여기 아래로)
    monkeypatch.setattr(po, "_backend_root", lambda: tmp_path)

    # 3) step registry 초기화 (테스트별 격리)
    saved = dict(_STEP_REGISTRY)
    _STEP_REGISTRY.clear()

    # 4) DB 스키마 초기화
    init_db()

    yield tmp_path

    _STEP_REGISTRY.clear()
    _STEP_REGISTRY.update(saved)


# ============================================================================
# Helpers
# ============================================================================

class TestCopySeedFiles:
    def test_copies_all_files(self, tmp_path):
        src1 = tmp_path / "a.txt"
        src2 = tmp_path / "b.md"
        src1.write_text("A")
        src2.write_text("B")
        dst = tmp_path / "dst"
        dst.mkdir()
        _copy_seed_files([src1, src2], dst)
        assert (dst / "a.txt").read_text() == "A"
        assert (dst / "b.md").read_text() == "B"

    def test_missing_file_raises(self, tmp_path):
        dst = tmp_path / "dst"
        dst.mkdir()
        with pytest.raises(FileNotFoundError, match="seed 파일 없음"):
            _copy_seed_files([tmp_path / "nope.txt"], dst)


class TestHashSeedFiles:
    def test_hashes_each_file(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")
        result = _hash_seed_files(tmp_path)
        assert set(result.keys()) == {"a.txt", "b.txt"}
        # SHA256 hex = 64 chars
        for h in result.values():
            assert len(h) == 64

    def test_skips_directories(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "subdir").mkdir()
        result = _hash_seed_files(tmp_path)
        assert list(result.keys()) == ["a.txt"]

    def test_empty_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert _hash_seed_files(empty) == {}


class TestSummarizeException:
    def test_basic(self):
        e = ValueError("oops")
        assert _summarize_exception(e) == "ValueError: oops"

    def test_truncates_long_messages(self):
        e = RuntimeError("x" * 500)
        result = _summarize_exception(e)
        assert result.startswith("RuntimeError: ")
        # truncated to <= 200 chars + "..."
        assert "..." in result
        # body 부분은 200자 이하
        body = result.split(": ", 1)[1]
        assert len(body) <= 200

    def test_empty_message_uses_class_name(self):
        class CustomErr(Exception):
            pass
        e = CustomErr()
        assert _summarize_exception(e) == "CustomErr: CustomErr"


class TestNowIso:
    def test_returns_z_suffixed_iso(self):
        s = po._now_iso()
        # YYYY-MM-DDTHH:MM:SSZ
        assert s.endswith("Z")
        assert "T" in s


# ============================================================================
# Step registry
# ============================================================================

class TestStepRegistry:
    def test_register_and_retrieve(self, isolated_pipeline):
        def fn(_ctx):
            return {}
        register_step("graph", fn)
        assert _get_step_fn("graph") is fn

    def test_register_unknown_step_raises(self, isolated_pipeline):
        with pytest.raises(ValueError, match="unknown step"):
            register_step("nonexistent", lambda _: {})

    def test_get_unregistered_step_raises(self, isolated_pipeline):
        with pytest.raises(RuntimeError, match="not registered"):
            _get_step_fn("graph")


# ============================================================================
# 예외
# ============================================================================

class TestExceptions:
    def test_run_not_found_carries_id(self):
        e = RunNotFound("r1")
        assert e.run_id == "r1"
        assert "r1" in str(e)

    def test_run_already_completed(self):
        e = RunAlreadyCompleted("r2")
        assert e.run_id == "r2"

    def test_run_cleanup_failed(self):
        e = RunCleanupFailed("r3")
        assert e.run_id == "r3"
        assert "Zep purge" in str(e)

    def test_zep_purge_failed(self):
        e = ZepPurgeFailed("r4", "connection lost")
        assert e.run_id == "r4"
        assert "connection lost" in str(e)

    def test_step_failed(self):
        e = StepFailed("graph", "boom")
        assert e.step == "graph"
        assert e.summary == "boom"

    def test_wall_clock_exceeded(self):
        e = WallClockExceeded("simulation", 1800)
        assert e.step == "simulation"
        assert e.limit == 1800


# ============================================================================
# DB init (멱등)
# ============================================================================

class TestInitDb:
    def test_idempotent(self, isolated_pipeline):
        # 이미 fixture 가 init 했음 — 다시 호출해도 예외 없음
        init_db()
        init_db()


# ============================================================================
# Orchestrator: start_run
# ============================================================================

class TestStartRun:
    def test_creates_run_with_seed_completed(self, isolated_pipeline, tmp_path, monkeypatch):
        # threading.Thread 차단 (백그라운드 실행 X)
        monkeypatch.setattr(po.threading, "Thread", _NoopThread)

        seed = tmp_path / "input.txt"
        seed.write_text("seed content")

        orch = PipelineOrchestrator()
        run_id = orch.start_run(
            seed_files=[seed],
            assumptions_version="v1",
        )
        assert isinstance(run_id, str)
        assert len(run_id) == 32  # uuid hex

        # DB: run 행 + seed_upload 완료 step 존재
        with po._db_conn() as conn:
            run_row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            step_row = conn.execute(
                "SELECT * FROM pipeline_steps WHERE run_id=? AND step_name='seed_upload'",
                (run_id,),
            ).fetchone()
        assert run_row is not None
        assert run_row["zep_group_id"] == f"run_{run_id}"
        assert run_row["assumptions_version"] == "v1"
        assert step_row is not None
        assert step_row["status"] == "completed"

        # seed 파일 복사됨
        seed_dir = po._step_final_dir(run_id, "seed_upload")
        assert (seed_dir / "input.txt").exists()

    def test_runs_to_completion_with_all_steps(self, isolated_pipeline, tmp_path, monkeypatch):
        monkeypatch.setattr(po.threading, "Thread", _InlineThread)

        # 모든 step 등록 — 빠르게 통과 (실제 어댑터처럼 tmp_dir 생성)
        def _fake_step(ctx):
            ctx.tmp_dir.mkdir(parents=True, exist_ok=True)
            return {"ok": True}

        for name in ("graph", "agents", "simulation", "report"):
            register_step(name, _fake_step)

        seed = tmp_path / "doc.txt"
        seed.write_text("data")

        orch = PipelineOrchestrator()
        run_id = orch.start_run(seed_files=[seed], assumptions_version="v1")

        # 모든 step 이 completed
        with po._db_conn() as conn:
            run_row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            steps = conn.execute(
                "SELECT step_name, status FROM pipeline_steps WHERE run_id=?",
                (run_id,),
            ).fetchall()
        assert run_row["status"] == "completed"
        for r in steps:
            assert r["status"] == "completed"

        # manifest 작성됨
        mpath = po._manifest_path(run_id)
        assert mpath.exists()
        manifest = json.loads(mpath.read_text())
        assert manifest["run_id"] == run_id
        assert manifest["status"] == "completed"
        # seed 해시 포함
        assert "seed_files" in manifest
        assert "doc.txt" in manifest["seed_files"]

    def test_failure_marks_run_failed(self, isolated_pipeline, tmp_path, monkeypatch):
        monkeypatch.setattr(po.threading, "Thread", _InlineThread)

        # 빠른 실패 — retry/backoff 시간 줄임
        monkeypatch.setattr(po, "retry_with_backoff", _no_retry_decorator)

        def _failing_step(ctx):
            raise RuntimeError("graph 폭발")

        register_step("graph", _failing_step)
        # 다른 step 은 실행되지 않을 것이므로 등록 불필요

        seed = tmp_path / "x.txt"
        seed.write_text("x")
        orch = PipelineOrchestrator()
        run_id = orch.start_run(seed_files=[seed], assumptions_version="v1")

        with po._db_conn() as conn:
            run_row = conn.execute(
                "SELECT status FROM pipeline_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            graph_step = conn.execute(
                "SELECT status, error_summary FROM pipeline_steps "
                "WHERE run_id=? AND step_name='graph'", (run_id,),
            ).fetchone()
        assert run_row["status"] == "failed"
        assert graph_step["status"] == "failed"
        assert "graph 폭발" in graph_step["error_summary"]


def _no_retry_decorator(*args, **kwargs):
    """retry_with_backoff 를 단순 단일실행으로 치환 (test 가속)."""
    def _wrap(fn):
        return fn
    return _wrap


# ============================================================================
# get_status
# ============================================================================

class TestGetStatus:
    def test_run_not_found(self, isolated_pipeline):
        orch = PipelineOrchestrator()
        with pytest.raises(RunNotFound):
            orch.get_status("ghost_run")

    def test_pending_run_lists_all_steps_as_pending(
        self, isolated_pipeline, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(po.threading, "Thread", _NoopThread)

        seed = tmp_path / "x.txt"
        seed.write_text("x")
        orch = PipelineOrchestrator()
        run_id = orch.start_run(seed_files=[seed], assumptions_version="v1")

        status = orch.get_status(run_id)
        assert status["run_id"] == run_id
        # seed_upload 만 완료, 나머지는 pending
        names = [s["name"] for s in status["steps"]]
        assert names == po.STEP_NAMES
        seed_step = next(s for s in status["steps"] if s["name"] == "seed_upload")
        assert seed_step["status"] == "completed"
        for s in status["steps"][1:]:
            assert s["status"] == "pending"
        assert status["error"] is None
        assert status["resumable_from"] is None

    def test_failed_step_populates_error_payload(
        self, isolated_pipeline, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(po.threading, "Thread", _InlineThread)
        monkeypatch.setattr(po, "retry_with_backoff", _no_retry_decorator)

        register_step("graph", lambda _: (_ for _ in ()).throw(RuntimeError("폭발")))

        seed = tmp_path / "x.txt"
        seed.write_text("x")
        orch = PipelineOrchestrator()
        run_id = orch.start_run(seed_files=[seed], assumptions_version="v1")

        status = orch.get_status(run_id)
        assert status["status"] == "failed"
        assert status["current_step"] == "graph"
        assert status["resumable_from"] == "graph"
        assert status["error"] is not None
        assert status["error"]["step"] == "graph"
        assert "폭발" in status["error"]["summary"]
        assert status["error"]["manifest_url"] == f"/api/pipeline/manifest/{run_id}"


# ============================================================================
# get_manifest
# ============================================================================

class TestGetManifest:
    def test_run_not_found(self, isolated_pipeline):
        orch = PipelineOrchestrator()
        with pytest.raises(RunNotFound):
            orch.get_manifest("ghost")

    def test_returns_manifest_after_completion(
        self, isolated_pipeline, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(po.threading, "Thread", _InlineThread)

        def _fake_step(ctx):
            ctx.tmp_dir.mkdir(parents=True, exist_ok=True)
            return {}

        for n in ("graph", "agents", "simulation", "report"):
            register_step(n, _fake_step)

        seed = tmp_path / "s.txt"
        seed.write_text("s")
        orch = PipelineOrchestrator()
        run_id = orch.start_run(seed_files=[seed], assumptions_version="v_x")

        manifest = orch.get_manifest(run_id)
        assert manifest["run_id"] == run_id
        assert manifest["status"] == "completed"
        assert manifest["assumptions_version"] == "v_x"
        # 5 step 기록
        assert len(manifest["steps"]) == 5


# ============================================================================
# _step_completed / _mark_run
# ============================================================================

class TestPrivateHelpers:
    def test_step_completed_false_when_missing(self, isolated_pipeline):
        orch = PipelineOrchestrator()
        assert orch._step_completed("ghost", "graph") is False

    def test_step_completed_true_after_insert(self, isolated_pipeline):
        # 직접 행 삽입
        with po._db_conn() as conn:
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, status, zep_group_id, "
                "assumptions_version, created_at, updated_at, manifest_json) "
                "VALUES ('r1', 'running', 'g', 'v', '2026-05-01', '2026-05-01', '{}')"
            )
            conn.execute(
                "INSERT INTO pipeline_steps (run_id, step_name, status, "
                "idempotency_key) VALUES ('r1', 'graph', 'completed', 'r1:graph')"
            )
        orch = PipelineOrchestrator()
        assert orch._step_completed("r1", "graph") is True
        assert orch._step_completed("r1", "agents") is False

    def test_mark_run_updates_status(self, isolated_pipeline):
        with po._db_conn() as conn:
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, status, zep_group_id, "
                "assumptions_version, created_at, updated_at, manifest_json) "
                "VALUES ('r1', 'running', 'g', 'v', '2026-05-01', '2026-05-01', '{}')"
            )
        orch = PipelineOrchestrator()
        orch._mark_run("r1", "completed")
        with po._db_conn() as conn:
            row = conn.execute(
                "SELECT status FROM pipeline_runs WHERE run_id='r1'"
            ).fetchone()
        assert row["status"] == "completed"


# ============================================================================
# resume_run
# ============================================================================

class TestResumeRun:
    def test_run_not_found(self, isolated_pipeline):
        orch = PipelineOrchestrator()
        with pytest.raises(RunNotFound):
            orch.resume_run("ghost")

    def test_already_completed(self, isolated_pipeline):
        with po._db_conn() as conn:
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, status, zep_group_id, "
                "assumptions_version, created_at, updated_at, manifest_json) "
                "VALUES ('done', 'completed', 'g', 'v1', '2026-05-01', '2026-05-01', '{}')"
            )
        orch = PipelineOrchestrator()
        with pytest.raises(RunAlreadyCompleted):
            orch.resume_run("done")

    def test_failed_cleanup_blocked(self, isolated_pipeline):
        with po._db_conn() as conn:
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, status, zep_group_id, "
                "assumptions_version, created_at, updated_at, manifest_json) "
                "VALUES ('clean', 'failed_cleanup', 'g', 'v1', '2026-05-01', '2026-05-01', '{}')"
            )
        orch = PipelineOrchestrator()
        with pytest.raises(RunCleanupFailed):
            orch.resume_run("clean")

    def test_purge_fail_marks_failed_cleanup(self, isolated_pipeline, monkeypatch):
        with po._db_conn() as conn:
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, status, zep_group_id, "
                "assumptions_version, created_at, updated_at, manifest_json) "
                "VALUES ('r1', 'failed', 'g_r1', 'v1', '2026-05-01', '2026-05-01', '{}')"
            )

        orch = PipelineOrchestrator()

        def _bad_purge(_self, _gid):
            raise RuntimeError("Neo4j 연결 끊김")

        monkeypatch.setattr(
            PipelineOrchestrator, "_purge_zep_group_with_retry", _bad_purge
        )
        with pytest.raises(ZepPurgeFailed):
            orch.resume_run("r1")
        # 이후 상태 확인
        with po._db_conn() as conn:
            row = conn.execute(
                "SELECT status FROM pipeline_runs WHERE run_id='r1'"
            ).fetchone()
        assert row["status"] == "failed_cleanup"

    def test_successful_purge_clears_steps_and_replays(
        self, isolated_pipeline, tmp_path, monkeypatch
    ):
        # run + 일부 step 데이터 미리 셋업
        run_id = "r_resume"
        with po._db_conn() as conn:
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, status, zep_group_id, "
                "assumptions_version, created_at, updated_at, manifest_json) "
                "VALUES (?, 'failed', 'g_z', 'v1', '2026-05-01', '2026-05-01', '{}')",
                (run_id,),
            )
            # seed_upload completed + graph failed
            conn.execute(
                "INSERT INTO pipeline_steps (run_id, step_name, status, "
                "idempotency_key) VALUES (?, 'seed_upload', 'completed', ?)",
                (run_id, f"{run_id}:seed_upload"),
            )
            conn.execute(
                "INSERT INTO pipeline_steps (run_id, step_name, status, "
                "idempotency_key, error_summary) "
                "VALUES (?, 'graph', 'failed', ?, '폭발')",
                (run_id, f"{run_id}:graph"),
            )

        # seed 디렉토리 + 파일 셋업 (resume 시 보존되어야 함)
        seed_final = po._step_final_dir(run_id, "seed_upload")
        seed_final.mkdir(parents=True, exist_ok=True)
        (seed_final / "input.txt").write_text("preserved")

        # 다른 step 산출 디렉토리 (제거 대상)
        graph_dir = po._step_final_dir(run_id, "graph")
        graph_dir.mkdir(parents=True, exist_ok=True)
        (graph_dir / "stale.json").write_text("stale")

        # purge 는 성공 처리
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_purge_zep_group_with_retry",
            lambda *a, **kw: None,
        )
        # _run_loop 도 차단 (resume 진행만 검증)
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_loop",
            lambda *a, **kw: None,
        )

        orch = PipelineOrchestrator()
        orch.resume_run(run_id)

        # 스텝 레코드 모두 삭제됨
        with po._db_conn() as conn:
            steps = conn.execute(
                "SELECT step_name FROM pipeline_steps WHERE run_id=?",
                (run_id,),
            ).fetchall()
            run = conn.execute(
                "SELECT status FROM pipeline_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        assert steps == []
        assert run["status"] == "pending"

        # graph 산출 디렉토리는 제거, seed_upload 는 보존
        assert not graph_dir.exists()
        assert (seed_final / "input.txt").read_text() == "preserved"
