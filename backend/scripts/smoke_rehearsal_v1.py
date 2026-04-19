"""
End-to-end 스모크: AI server / SI wafer v1 파이프라인 1회 실행.

orchestrator.start_run을 직접 호출 (Flask 경유 X). 11개 seed 마크다운 +
assumptions v1을 실제 LLM/Zep/OASIS에 태워 5단계 완주 여부 확인.

Usage:
    cd backend && uv run python scripts/smoke_rehearsal_v1.py

환경 변수:
    SMOKE_MAX_ROUNDS (default 20) — OASIS 라운드 한도
    SMOKE_SEED_DIR (default 부모 레포 seed_documents/ai_server_si_wafer/)
"""
import os
import sys
import time
import json
from pathlib import Path

HERE = Path(__file__).resolve()
BACKEND = HERE.parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.pipeline_orchestrator import PipelineOrchestrator  # noqa: E402
from app.services import pipeline_adapters  # noqa: E402,F401  (register_step 부작용)
from app.utils.assumptions_loader import load_assumptions_text  # noqa: E402


def main():
    # ── seed files ──────────────────────────────────────────────
    default_seed = (
        BACKEND.parent.parent
        / 'seed_documents'
        / 'ai_server_si_wafer'
    )
    seed_dir = Path(os.environ.get('SMOKE_SEED_DIR', default_seed))
    if not seed_dir.exists():
        raise SystemExit(f'seed dir 없음: {seed_dir}')
    seed_files = sorted(seed_dir.glob('*.md'))
    if not seed_files:
        raise SystemExit(f'seed dir에 .md 없음: {seed_dir}')

    total_bytes = sum(p.stat().st_size for p in seed_files)
    print(f'■ seed: {len(seed_files)} files, {total_bytes / 1024:.1f} KB')
    for p in seed_files:
        print(f'    - {p.name} ({p.stat().st_size} B)')

    # ── assumptions ─────────────────────────────────────────────
    version = 'ai_server_si_wafer_v1'
    assumptions_text = load_assumptions_text(version)
    print(f'■ assumptions: {version}, narrative {len(assumptions_text):,} chars')

    # ── extra_config ────────────────────────────────────────────
    max_rounds = int(os.environ.get('SMOKE_MAX_ROUNDS', '20'))
    extra_config = {
        'assumptions_text': assumptions_text,
        'simulation_max_rounds': max_rounds,
        'enable_twitter': True,
        'enable_reddit': True,
        'parallel_profile_count': 3,
        'simulation_requirement': (
            'AI 서버 수요 사이클 및 SI 웨이퍼 공급망의 2026년 2분기 여론 전파 '
            '시뮬레이션. 하이퍼스케일러 capex 사이클, HBM 병목, TSMC CoWoS 증설, '
            '대만/한국 공급망 이슈를 중심으로 각 에이전트의 입장을 반영.'
        ),
    }
    print(f'■ max_rounds={max_rounds}, twitter=T, reddit=T')

    # ── run ─────────────────────────────────────────────────────
    orch = PipelineOrchestrator()
    print(f'■ start_run 호출 중...')
    run_id = orch.start_run(
        seed_files=seed_files,
        assumptions_version=version,
        extra_config=extra_config,
    )
    print(f'■ run_id = {run_id}')
    started = time.time()

    # ── poll ────────────────────────────────────────────────────
    last_step = None
    last_tick = time.time()
    tick_interval = 10  # 10초 간격 상태 리포트
    while True:
        status = orch.get_status(run_id)
        current_step = status.get('current_step')
        run_status = status.get('status')
        error = status.get('error')

        # 상태 변화 감지
        if current_step != last_step:
            elapsed = time.time() - started
            print(f'  [{elapsed:6.1f}s] step: {last_step or "init"} → {current_step or "—"} (run_status={run_status})')
            last_step = current_step
            last_tick = time.time()
        elif time.time() - last_tick > tick_interval:
            elapsed = time.time() - started
            for s in status['steps']:
                if s['status'] == 'running':
                    print(f'  [{elapsed:6.1f}s] {s["name"]} running '
                          f'(duration={s["duration_s"]}s, llm_calls={s["llm_calls"]}, retry={s["retry_count"]})')
            last_tick = time.time()

        if run_status in ('completed', 'failed'):
            break
        if error:
            break
        time.sleep(3)

    elapsed = time.time() - started

    # ── final report ────────────────────────────────────────────
    print('\n' + '=' * 60)
    print(f'■ FINAL run_status={status["status"]} elapsed={elapsed:.1f}s')
    print('=' * 60)
    print('\nStep-by-step:')
    for s in status['steps']:
        badge = {
            'pending': '⏸',
            'running': '▶',
            'completed': '✅',
            'failed': '❌',
        }.get(s['status'], '?')
        print(f'  {badge} {s["name"]:12s} status={s["status"]:9s} '
              f'duration={s["duration_s"]:>5.1f}s  llm={s["llm_calls"]:>3d}  retry={s["retry_count"]}')

    if status.get('error'):
        print('\n❌ ERROR:')
        print(json.dumps(status['error'], indent=2, ensure_ascii=False))

    # manifest 요약
    try:
        manifest = orch.get_manifest(run_id)
        print('\n■ manifest.steps_meta keys:', list(manifest.get('steps', {}).keys()))
    except Exception as e:
        print(f'  (manifest load 실패: {e})')

    # 비용 추정
    total_llm = sum(s['llm_calls'] for s in status['steps'])
    print(f'\n■ 총 LLM 호출: {total_llm}회')

    # exit code
    sys.exit(0 if status['status'] == 'completed' else 1)


if __name__ == '__main__':
    main()
