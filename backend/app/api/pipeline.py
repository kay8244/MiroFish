"""
Pipeline API Blueprint

5단계 파이프라인 실행을 웹에서 end-to-end 자동 완주시키기 위한 REST 엔드포인트.

- POST   /api/pipeline/run              새 run 시작 (seed 업로드 + 즉시 실행)
- GET    /api/pipeline/status/<run_id>  A3 스키마 상태 조회 (UI polling)
- GET    /api/pipeline/manifest/<run_id> Run Manifest JSON
- POST   /api/pipeline/resume/<run_id>  실패한 run 재개 (Zep purge → 재실행)

기존 2,765라인 api/simulation.py는 건드리지 않는다. 이 blueprint는
app/__init__.py에서 pipeline_bp로 별도 등록된다.

에러 응답 스키마는 디자인 문서 Architecture Addendum A3 참조.
"""

import threading
from pathlib import Path

from flask import Blueprint, request, jsonify

from ..services.pipeline_orchestrator import (
    PipelineOrchestrator,
    RunNotFound,
    RunAlreadyCompleted,
    RunCleanupFailed,
    ZepPurgeFailed,
)
from ..utils.logger import get_logger

pipeline_bp = Blueprint('pipeline', __name__)
logger = get_logger('mirofish.api.pipeline')

# 동시 run은 단일 빌더 MVP에서 1개만 돌린다고 가정하지만, 오케스트레이터는
# 비동기로 실행하여 HTTP 응답이 긴 작업에 묶이지 않도록 한다.
_orchestrator = PipelineOrchestrator()


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _uploads_root() -> Path:
    return _backend_root() / 'uploads'


# ─────────────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────────────

@pipeline_bp.route('/run', methods=['POST'])
def start_run():
    """새 파이프라인 run 시작.

    요청:
      multipart/form-data
        seed_files: 파일 목록 (PDF/MD/TXT, 개당 최대 50MB)
        assumptions_version: YAML 버전 문자열 (예: "ai_server_si_wafer_v1")

    응답:
      202 Accepted
      {
        "run_id": "<hex>",
        "status_url": "/api/pipeline/status/<run_id>"
      }

      400 Bad Request - seed 파일 누락 / 포맷 불일치
      413 Payload Too Large - 50MB 초과
    """
    files = request.files.getlist('seed_files')
    if not files:
        return jsonify({
            'error': 'missing_seed_files',
            'message': 'seed_files 폼 필드가 필요합니다.',
        }), 400

    assumptions_version = request.form.get('assumptions_version', 'ai_server_si_wafer_v1')

    # 일시 업로드 저장 (seed_upload 단계 입력으로 전달)
    staging_dir = _uploads_root() / 'staging'
    staging_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    for f in files:
        if not f.filename:
            continue
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext not in ('pdf', 'md', 'txt'):
            return jsonify({
                'error': 'unsupported_format',
                'message': f'지원하지 않는 포맷: {f.filename} (PDF/MD/TXT만 허용)',
            }), 400
        p = staging_dir / f.filename
        f.save(str(p))
        size = p.stat().st_size
        if size > 50 * 1024 * 1024:
            p.unlink(missing_ok=True)
            return jsonify({
                'error': 'file_too_large',
                'message': f'파일 용량 초과 (최대 50MB): {f.filename}',
            }), 413
        saved_paths.append(p)

    if not saved_paths:
        return jsonify({
            'error': 'no_valid_files',
            'message': 'seed 파일이 하나도 저장되지 않았습니다.',
        }), 400

    # 비동기 실행: 스레드로 띄워서 HTTP 응답은 즉시 반환
    # (Flask dev 서버 기준. 프로덕션은 WSGI worker 또는 Celery 필요 — Phase 2)
    import uuid
    preliminary_run_id = uuid.uuid4().hex  # 로그용
    logger.info(f'run 시작 요청 수신 (preliminary_id={preliminary_run_id})')

    run_id_holder = {'id': None, 'error': None}
    done = threading.Event()

    def _start():
        try:
            rid = _orchestrator.start_run(
                seed_files=saved_paths,
                assumptions_version=assumptions_version,
            )
            run_id_holder['id'] = rid
        except Exception as e:
            logger.exception(f'start_run 예외: {e}')
            run_id_holder['error'] = str(e)
        finally:
            done.set()

    t = threading.Thread(target=_start, daemon=True)
    t.start()

    # start_run이 DB INSERT + seed 복사까지 마치고 run_id를 확보한 뒤 리턴하도록
    # 짧게 대기한다. 이후 긴 작업(LLM 호출 등)은 백그라운드에서 계속 진행.
    # 완전 논블로킹으로 만들려면 job queue 도입이 정석 (Phase 2).
    done.wait(timeout=10.0)
    if run_id_holder['error']:
        return jsonify({
            'error': 'start_failed',
            'message': run_id_holder['error'],
        }), 500
    if run_id_holder['id'] is None:
        # 10초 안에 run_id 확보 못 함 = seed 복사 느림 또는 에러. 일단 폴링 안내.
        return jsonify({
            'error': 'start_slow',
            'message': '초기화가 오래 걸립니다. 잠시 후 /api/pipeline/status 폴링 권장.',
        }), 504

    run_id = run_id_holder['id']
    return jsonify({
        'run_id': run_id,
        'status_url': f'/api/pipeline/status/{run_id}',
    }), 202


@pipeline_bp.route('/status/<run_id>', methods=['GET'])
def get_status(run_id: str):
    """A3 스키마 상태 응답. UI가 2초 간격으로 polling."""
    try:
        status = _orchestrator.get_status(run_id)
    except RunNotFound:
        return jsonify({
            'error': 'run_not_found',
            'run_id': run_id,
        }), 404
    return jsonify(status), 200


@pipeline_bp.route('/manifest/<run_id>', methods=['GET'])
def get_manifest(run_id: str):
    try:
        manifest = _orchestrator.get_manifest(run_id)
    except RunNotFound:
        return jsonify({
            'error': 'run_not_found',
            'run_id': run_id,
        }), 404
    return jsonify(manifest), 200


@pipeline_bp.route('/resume/<run_id>', methods=['POST'])
def resume_run(run_id: str):
    """실패한 run 재개. Zep purge 3회 실패 시 409 Conflict."""
    def _do_resume():
        _orchestrator.resume_run(run_id)

    try:
        # 비동기 실행 (start_run과 동일 패턴)
        t = threading.Thread(target=_do_resume, daemon=True)
        t.start()
        return jsonify({
            'run_id': run_id,
            'status_url': f'/api/pipeline/status/{run_id}',
            'message': 'resume 시작',
        }), 202
    except RunNotFound:
        return jsonify({'error': 'run_not_found', 'run_id': run_id}), 404
    except RunAlreadyCompleted:
        return jsonify({
            'error': 'run_already_completed',
            'run_id': run_id,
            'message': '이미 완료된 run입니다.',
        }), 409
    except RunCleanupFailed:
        return jsonify({
            'error': 'zep_purge_failed',
            'run_id': run_id,
            'message': 'Zep purge 3회 재시도 실패. 새 run을 시작해주세요.',
        }), 409
    except ZepPurgeFailed as e:
        return jsonify({
            'error': 'zep_purge_failed',
            'run_id': run_id,
            'message': str(e),
        }), 409
