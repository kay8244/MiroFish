"""
simulation 패키지 공유 헬퍼

여러 도메인 모듈에서 공통으로 사용하는 유틸리티:
- BACKEND_DIR: backend/ 디렉토리 절대경로 (sub-module 깊이 무관)
- _validate_pagination: 페이지네이션 파라미터 검증
- INTERVIEW_PROMPT_PREFIX / optimize_interview_prompt: 인터뷰 프롬프트 최적화
- _check_simulation_prepared: 시뮬레이션 준비 완료 여부 확인
- _get_report_id_for_simulation: 시뮬레이션에 매칭되는 최신 report_id 검색
"""

import json
import os
from datetime import datetime

from ...config import Config
from ...utils.logger import get_logger

logger = get_logger('mirofish.api.simulation')

# backend/ 디렉토리 절대경로
# 이 파일은 backend/app/api/simulation/_shared.py 에 위치하므로 4단계 위가 backend/
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


def _validate_pagination(request_args, max_limit=100, default_limit=20):
    """페이지네이션 파라미터 검증"""
    try:
        limit = int(request_args.get('limit', default_limit))
    except (ValueError, TypeError):
        limit = default_limit

    try:
        offset = int(request_args.get('offset', 0))
    except (ValueError, TypeError):
        offset = 0

    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset


# Interview prompt 최적화 접두어
# 이 접두어를 추가하면 Agent가 도구를 호출하지 않고 텍스트로 직접 응답
INTERVIEW_PROMPT_PREFIX = "당신의 페르소나, 모든 과거 기억과 행동을 바탕으로, 어떤 도구도 호출하지 말고 텍스트로 직접 답해주세요："


def optimize_interview_prompt(prompt: str) -> str:
    """
    Interview 질문 최적화 - Agent가 도구를 호출하지 않도록 접두어 추가

    Args:
        prompt: 원래 질문

    Returns:
        최적화된 질문
    """
    if not prompt:
        return prompt
    # 접두어 중복 추가 방지
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    시뮬레이션 준비 완료 여부 확인

    확인 조건:
    1. state.json 존재 및 status가 "ready"
    2. 필수 파일 존재: reddit_profiles.json, twitter_profiles.csv, simulation_config.json

    참고: 실행 스크립트(run_*.py)는 backend/scripts/ 디렉토리에 유지되며, 시뮬레이션 디렉토리에 복사되지 않음

    Args:
        simulation_id: 시뮬레이션 ID

    Returns:
        (is_prepared: bool, info: dict)
    """
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

    # 디렉토리 존재 여부 확인
    if not os.path.exists(simulation_dir):
        return False, {"reason": "시뮬레이션 디렉토리가 존재하지 않음"}

    # 필수 파일 목록 (스크립트 제외, 스크립트는 backend/scripts/ 에 위치)
    required_files = [
        "state.json",
        "simulation_config.json",
        "reddit_profiles.json",
        "twitter_profiles.csv"
    ]

    # 파일 존재 여부 확인
    existing_files = []
    missing_files = []
    for f in required_files:
        file_path = os.path.join(simulation_dir, f)
        if os.path.exists(file_path):
            existing_files.append(f)
        else:
            missing_files.append(f)

    if missing_files:
        return False, {
            "reason": "필수 파일 누락",
            "missing_files": missing_files,
            "existing_files": existing_files
        }

    # state.json 의 상태 확인
    state_file = os.path.join(simulation_dir, "state.json")
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)

        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)

        # 상세 로그
        logger.debug(f"시뮬레이션 준비 상태 확인: {simulation_id}, status={status}, config_generated={config_generated}")

        # config_generated=True 이고 파일이 존재하면 준비 완료로 판단
        # 아래 상태는 모두 준비 작업이 완료되었음을 의미:
        # - ready: 준비 완료, 실행 가능
        # - preparing: config_generated=True 이면 완료됨
        # - running: 실행 중, 준비는 이미 완료됨
        # - completed: 실행 완료, 준비는 이미 완료됨
        # - stopped: 중지됨, 준비는 이미 완료됨
        # - failed: 실행 실패 (준비는 완료됨)
        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            # 파일 통계 정보 가져오기
            profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")

            profiles_count = 0
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    profiles_data = json.load(f)
                    profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0

            # 상태가 preparing 이지만 파일이 완료된 경우, 자동으로 ready 로 업데이트
            if status == "preparing":
                try:
                    state_data["status"] = "ready"
                    state_data["updated_at"] = datetime.now().isoformat()
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"시뮬레이션 상태 자동 업데이트: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as e:
                    logger.warning(f"상태 자동 업데이트 실패: {e}")

            logger.info(f"시뮬레이션 {simulation_id} 확인 결과: 준비 완료 (status={status}, config_generated={config_generated})")
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files
            }
        else:
            logger.warning(f"시뮬레이션 {simulation_id} 확인 결과: 준비 미완료 (status={status}, config_generated={config_generated})")
            return False, {
                "reason": f"상태가 준비 완료 목록에 없거나 config_generated가 false: status={status}, config_generated={config_generated}",
                "status": status,
                "config_generated": config_generated
            }

    except Exception as e:
        return False, {"reason": f"상태 파일 읽기 실패: {str(e)}"}


def _get_report_id_for_simulation(simulation_id: str) -> str:
    """
    시뮬레이션에 해당하는 최신 report_id 가져오기

    reports 디렉토리를 순회하여 simulation_id 와 일치하는 report 검색,
    여러 개인 경우 가장 최신 것 반환 (created_at 기준 정렬)

    Args:
        simulation_id: 시뮬레이션 ID

    Returns:
        report_id 또는 None
    """
    reports_dir = os.path.join(BACKEND_DIR, 'uploads', 'reports')
    if not os.path.exists(reports_dir):
        return None

    matching_reports = []

    try:
        for report_folder in os.listdir(reports_dir):
            report_path = os.path.join(reports_dir, report_folder)
            if not os.path.isdir(report_path):
                continue

            meta_file = os.path.join(report_path, "meta.json")
            if not os.path.exists(meta_file):
                continue

            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)

                if meta.get("simulation_id") == simulation_id:
                    matching_reports.append({
                        "report_id": meta.get("report_id"),
                        "created_at": meta.get("created_at", ""),
                        "status": meta.get("status", "")
                    })
            except Exception:
                continue

        if not matching_reports:
            return None

        # 생성 시간 역순 정렬, 가장 최신 것 반환
        matching_reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matching_reports[0].get("report_id")

    except Exception as e:
        logger.warning(f"simulation {simulation_id} 의 report 검색 실패: {e}")
        return None
