"""
5회 연속 리허설 게이트.

기본 비활성화 (유닛 테스트 실행 시 스킵). 환경변수 ``MIROFISH_REHEARSAL=1``로
활성화. 활성화 시 실제 LLM/Zep/OASIS를 호출해 smoke_rehearsal_v1을 N회 반복하고
결과를 JSON 리포트로 기록한다.

Day 2 PM 게이트:
    MIROFISH_REHEARSAL=1 uv run pytest tests/test_rehearsal_5runs.py -s

판정:
    - 4+/5 통과 → Day 3 진행
    - 2+/5 실패 → Assumptions UI 드롭 (scope 축소)
    - 5/5 실패 → 상류 이슈 (quota, Zep, adapter) 근본 원인 우선 조사

환경변수:
    MIROFISH_REHEARSAL (default 0) — 1이면 실행
    MIROFISH_REHEARSAL_RUNS (default 5) — 반복 횟수
    MIROFISH_REHEARSAL_MAX_ROUNDS (default 20) — OASIS 라운드 한도
    MIROFISH_REHEARSAL_REPORT (default .planning/rehearsal_<ts>.json)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


REHEARSAL_ENABLED = os.environ.get("MIROFISH_REHEARSAL") == "1"


def _require_enabled():
    if not REHEARSAL_ENABLED:
        pytest.skip(
            "리허설 게이트는 기본 비활성화. `MIROFISH_REHEARSAL=1`로 활성화.",
            allow_module_level=False,
        )


def _seed_dir() -> Path:
    """기본 seed 경로 — 부모 레포의 seed_documents/ai_server_si_wafer/."""
    default = (
        Path(__file__).resolve().parents[2].parent
        / "seed_documents"
        / "ai_server_si_wafer"
    )
    return Path(os.environ.get("MIROFISH_REHEARSAL_SEED", default))


def _run_one_iteration(
    iteration_idx: int,
    max_rounds: int,
    assumptions_version: str,
) -> dict:
    """단일 리허설 iteration — smoke_rehearsal_v1과 같은 로직을 inline 실행."""
    from app.services.pipeline_orchestrator import PipelineOrchestrator
    from app.services import pipeline_adapters  # noqa: F401 (register_step 부작용)
    from app.utils.assumptions_loader import load_assumptions_text

    seed = _seed_dir()
    seed_files = sorted(seed.glob("*.md")) if seed.exists() else []
    if not seed_files:
        return {
            "iteration": iteration_idx,
            "status": "skipped",
            "reason": f"seed dir 또는 *.md 없음: {seed}",
        }

    assumptions_text = load_assumptions_text(assumptions_version)
    extra_config = {
        "assumptions_text": assumptions_text,
        "simulation_max_rounds": max_rounds,
        "enable_twitter": True,
        "enable_reddit": True,
        "parallel_profile_count": 3,
    }

    orch = PipelineOrchestrator()
    started = time.time()
    run_id = orch.start_run(
        seed_files=seed_files,
        assumptions_version=assumptions_version,
        extra_config=extra_config,
    )

    # 2초 간격 폴링, 최대 35분 wall-clock
    deadline = started + 35 * 60
    final_status: Optional[dict] = None
    while time.time() < deadline:
        st = orch.get_status(run_id)
        if st["status"] in ("completed", "failed"):
            final_status = st
            break
        time.sleep(2)

    elapsed = time.time() - started
    if final_status is None:
        return {
            "iteration": iteration_idx,
            "run_id": run_id,
            "status": "timeout",
            "elapsed_s": round(elapsed, 1),
            "reason": "35분 wall-clock 초과",
        }

    steps = final_status.get("steps", [])
    total_llm = sum(s.get("llm_calls", 0) for s in steps)
    total_retry = sum(s.get("retry_count", 0) for s in steps)
    failed_step = None
    for s in steps:
        if s.get("status") == "failed":
            failed_step = s.get("name")
            break

    return {
        "iteration": iteration_idx,
        "run_id": run_id,
        "status": final_status["status"],
        "elapsed_s": round(elapsed, 1),
        "total_llm_calls": total_llm,
        "total_retries": total_retry,
        "failed_step": failed_step,
        "error": final_status.get("error"),
        "steps": [
            {
                "name": s["name"],
                "status": s.get("status"),
                "duration_s": s.get("duration_s", 0),
                "llm_calls": s.get("llm_calls", 0),
                "retry_count": s.get("retry_count", 0),
            }
            for s in steps
        ],
    }


def _write_report(report: dict) -> Path:
    default = (
        Path(__file__).resolve().parents[2].parent
        / ".planning"
        / f"rehearsal_{int(time.time())}.json"
    )
    out = Path(os.environ.get("MIROFISH_REHEARSAL_REPORT", default))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


@pytest.mark.slow
def test_five_consecutive_rehearsal_runs():
    _require_enabled()

    runs = int(os.environ.get("MIROFISH_REHEARSAL_RUNS", "5"))
    max_rounds = int(os.environ.get("MIROFISH_REHEARSAL_MAX_ROUNDS", "20"))
    version = os.environ.get(
        "MIROFISH_REHEARSAL_ASSUMPTIONS", "ai_server_si_wafer_v1"
    )

    print(
        f"\n▶ 리허설 {runs}회 시작 (max_rounds={max_rounds}, assumptions={version})\n"
    )

    results = []
    start = time.time()
    for i in range(1, runs + 1):
        print(f"── iteration {i}/{runs} ──")
        r = _run_one_iteration(i, max_rounds, version)
        results.append(r)
        status = r["status"]
        marker = {"completed": "✅", "failed": "❌"}.get(status, "⏳")
        print(
            f"{marker} #{i} status={status} "
            f"elapsed={r.get('elapsed_s', '-')}s "
            f"llm={r.get('total_llm_calls', '-')} "
            f"retry={r.get('total_retries', '-')} "
            f"failed_step={r.get('failed_step') or '—'}"
        )
    total_elapsed = round(time.time() - start, 1)

    passed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] in ("failed", "timeout"))
    skipped = sum(1 for r in results if r["status"] == "skipped")

    report = {
        "assumptions_version": version,
        "max_rounds": max_rounds,
        "runs": runs,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total_elapsed_s": total_elapsed,
        "results": results,
    }
    out = _write_report(report)

    print("\n" + "=" * 60)
    print(f"리허설 결과: pass={passed}/{runs}, fail={failed}, skip={skipped}")
    print(f"리포트: {out}")
    print("=" * 60)

    # 판정: 4+/runs 통과
    threshold = max(1, int(runs * 0.8))  # 5회 → 4, 3회 → 2
    assert passed >= threshold, (
        f"리허설 실패: 통과 {passed}/{runs} < 임계값 {threshold}. "
        f"리포트: {out}"
    )
