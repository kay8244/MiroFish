"""
시뮬레이션 관련 API 라우트
Step2: Zep 엔티티 읽기 및 필터링, OASIS 시뮬레이션 준비 및 실행 (전체 자동화)
"""

import os
import traceback
from flask import request, jsonify, send_file

from .. import simulation_bp
from ...config import Config
from ...services.graphiti_entity_reader import GraphitiEntityReader
from ...services.oasis_profile_generator import OasisProfileGenerator
from ...services.simulation_manager import SimulationManager, SimulationStatus
from ...services.simulation_runner import SimulationRunner, RunnerStatus, SimulationLimitError
from ...utils.logger import get_logger
from ...utils.cache import entity_cache
from ...models.project import ProjectManager
from ...utils.rate_limiter import rate_limit

from ._shared import (
    BACKEND_DIR,
    INTERVIEW_PROMPT_PREFIX,
    _check_simulation_prepared,
    _get_report_id_for_simulation,
    _validate_pagination,
    optimize_interview_prompt,
)

logger = get_logger('mirofish.api.simulation')

# 도메인별 라우트 모듈 등록 (import 시점에 @simulation_bp.route 데코레이터 실행)
from . import entities  # noqa: E402, F401
from . import activity  # noqa: E402, F401
from . import config as _config_routes  # noqa: E402, F401
from . import interview  # noqa: E402, F401


# ============== 시뮬레이션 관리 인터페이스 ==============

@simulation_bp.route('/create', methods=['POST'])
@rate_limit(max_requests=3, period_seconds=60)
def create_simulation():
    """
    새 시뮬레이션 생성

    참고: max_rounds 등 파라미터는 LLM이 지능적으로 생성하므로 수동 설정 불필요

    요청 (JSON):
        {
            "project_id": "proj_xxxx",      // 필수
            "graph_id": "mirofish_xxxx",    // 선택적, 제공하지 않으면 project에서 가져옴
            "enable_twitter": true,          // 선택적, 기본값 true
            "enable_reddit": true            // 선택적, 기본값 true
        }

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "project_id": "proj_xxxx",
                "graph_id": "mirofish_xxxx",
                "status": "created",
                "enable_twitter": true,
                "enable_reddit": true,
                "created_at": "2025-12-01T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}

        project_id = data.get('project_id')
        if not project_id:
            return jsonify({
                "success": False,
                "error": "project_id 를 제공해주세요"
            }), 400

        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"프로젝트가 존재하지 않음: {project_id}"
            }), 404

        graph_id = data.get('graph_id') or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "프로젝트에 그래프가 아직 구축되지 않았습니다. 먼저 /api/graph/build 를 호출해주세요"
            }), 400

        # B 시나리오: simulation_requirement 오버라이드 허용.
        # 지정 시 이 sim 에만 적용되고, 생략 시 prepare 에서 project 값으로 fallback.
        sim_requirement_override = data.get('simulation_requirement')
        if sim_requirement_override is not None:
            sim_requirement_override = str(sim_requirement_override).strip() or None

        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=data.get('enable_twitter', True),
            enable_reddit=data.get('enable_reddit', True),
            simulation_requirement=sim_requirement_override,
        )

        return jsonify({
            "success": True,
            "data": state.to_dict()
        })

    except Exception as e:
        logger.error(f"시뮬레이션 생성 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/prepare', methods=['POST'])
@rate_limit(max_requests=3, period_seconds=60)
def prepare_simulation():
    """
    시뮬레이션 환경 준비 (비동기 태스크, LLM이 모든 파라미터를 지능적으로 생성)

    시간이 걸리는 작업으로, 인터페이스는 즉시 task_id를 반환하며,
    GET /api/simulation/prepare/status 를 통해 진행 상황 조회 가능

    특징:
    - 완료된 준비 작업 자동 감지, 중복 생성 방지
    - 이미 준비 완료된 경우 기존 결과 바로 반환
    - 강제 재생성 지원 (force_regenerate=true)

    단계:
    1. 완료된 준비 작업 여부 확인
    2. Zep 그래프에서 엔티티 읽기 및 필터링
    3. 각 엔티티에 대한 OASIS Agent Profile 생성 (재시도 메커니즘 포함)
    4. LLM 지능형 시뮬레이션 설정 생성 (재시도 메커니즘 포함)
    5. 설정 파일 및 사전 설정 스크립트 저장

    요청 (JSON):
        {
            "simulation_id": "sim_xxxx",                   // 필수, 시뮬레이션 ID
            "entity_types": ["Student", "PublicFigure"],  // 선택적, 엔티티 유형 지정
            "use_llm_for_profiles": true,                 // 선택적, LLM으로 페르소나 생성 여부
            "parallel_profile_count": 5,                  // 선택적, 병렬 페르소나 생성 수, 기본값 5
            "force_regenerate": false                     // 선택적, 강제 재생성, 기본값 false
        }

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",           // 새 태스크 시 반환
                "status": "preparing|ready",
                "message": "준비 태스크 시작됨|이미 완료된 준비 작업 있음",
                "already_prepared": true|false    // 이미 준비 완료 여부
            }
        }
    """
    import threading
    import os
    from ..models.task import TaskManager, TaskStatus
    from ..config import Config
    
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id 를 제공해주세요"
            }), 400

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"시뮬레이션이 존재하지 않음: {simulation_id}"
            }), 404

        # 강제 재생성 여부 확인
        force_regenerate = data.get('force_regenerate', False)
        logger.info(f"/prepare 요청 처리 시작: simulation_id={simulation_id}, force_regenerate={force_regenerate}")

        # 이미 준비 완료 여부 확인 (중복 생성 방지)
        if not force_regenerate:
            logger.debug(f"시뮬레이션 {simulation_id} 준비 완료 여부 확인 중...")
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            logger.debug(f"확인 결과: is_prepared={is_prepared}, prepare_info={prepare_info}")
            if is_prepared:
                logger.info(f"시뮬레이션 {simulation_id} 이미 준비 완료, 중복 생성 건너뜀")
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "message": "이미 완료된 준비 작업이 있습니다. 중복 생성 불필요",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
            else:
                logger.info(f"시뮬레이션 {simulation_id} 준비 미완료, 준비 태스크 시작")

        # 프로젝트에서 필요한 정보 가져오기
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"프로젝트가 존재하지 않음: {state.project_id}"
            }), 404

        # 시뮬레이션 요구사항: state 오버라이드 > project 기본값 (B 시나리오 지원).
        # payload 로 이번 prepare 호출에서만 오버라이드도 허용.
        prepare_override = data.get('simulation_requirement')
        if prepare_override is not None:
            prepare_override = str(prepare_override).strip() or None
        if prepare_override:
            # 이번 prepare 호출 내내 이 값을 사용하고 state 에도 영구 반영
            state.simulation_requirement = prepare_override
            manager._save_simulation_state(state)
        simulation_requirement = (
            state.simulation_requirement
            or project.simulation_requirement
            or ""
        )
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "시뮬레이션 요구사항이 없습니다 (simulation/create 의 simulation_requirement 또는 project.simulation_requirement 중 하나 필요)"
            }), 400

        # 문서 텍스트 가져오기
        document_text = ProjectManager.get_extracted_text(state.project_id) or ""

        entity_types_list = data.get('entity_types')
        use_llm_for_profiles = data.get('use_llm_for_profiles', True)
        parallel_profile_count = data.get('parallel_profile_count', 5)

        # ========== 동기적 엔티티 수 조회 (백그라운드 태스크 시작 전) ==========
        # 이를 통해 프론트엔드가 prepare 호출 직후 예상 Agent 총 수를 바로 가져올 수 있음
        try:
            logger.info(f"동기적 엔티티 수 조회: graph_id={state.graph_id}")
            reader = GraphitiEntityReader()
            # 빠른 엔티티 읽기 (엣지 정보 불필요, 수만 집계)
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False  # 엣지 정보 조회 안 함, 속도 향상
            )
            # 엔티티 수를 상태에 저장 (프론트엔드가 즉시 조회 가능)
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(f"예상 엔티티 수: {filtered_preview.filtered_count}, 유형: {filtered_preview.entity_types}")
        except Exception as e:
            logger.warning(f"동기적 엔티티 수 조회 실패 (백그라운드 태스크에서 재시도): {e}")
            # 실패해도 후속 프로세스에 영향 없음, 백그라운드 태스크에서 재조회

        # 비동기 태스크 생성
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={
                "simulation_id": simulation_id,
                "project_id": state.project_id
            }
        )

        # 시뮬레이션 상태 업데이트 (미리 조회한 엔티티 수 포함)
        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)

        # 백그라운드 태스크 정의
        def run_prepare():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="시뮬레이션 환경 준비 시작..."
                )

                # 시뮬레이션 준비 (진행 상황 콜백 포함)
                # 단계별 진행 상세 정보 저장
                stage_details = {}

                def progress_callback(stage, progress, message, **kwargs):
                    # 전체 진행률 계산
                    stage_weights = {
                        "reading": (0, 20),               # 0-20%
                        "generating_profiles": (20, 70),  # 20-70%
                        "generating_config": (70, 90),    # 70-90%
                        "copying_scripts": (90, 100)      # 90-100%
                    }

                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)

                    # 상세 진행 정보 구성
                    stage_names = {
                        "reading": "그래프 엔티티 읽기",
                        "generating_profiles": "Agent 페르소나 생성",
                        "generating_config": "시뮬레이션 설정 생성",
                        "copying_scripts": "시뮬레이션 스크립트 준비"
                    }

                    stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    total_stages = len(stage_weights)

                    # 단계 상세 업데이트
                    stage_details[stage] = {
                        "stage_name": stage_names.get(stage, stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                        "item_name": kwargs.get("item_name", "")
                    }

                    # 상세 진행 정보 구성
                    detail = stage_details[stage]
                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": stage_names.get(stage, stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message
                    }

                    # 간결한 메시지 구성
                    if detail["total"] > 0:
                        detailed_message = (
                            f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                            f"{detail['current']}/{detail['total']} - {message}"
                        )
                    else:
                        detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"

                    task_manager.update_task(
                        task_id,
                        progress=current_progress,
                        message=detailed_message,
                        progress_detail=progress_detail_data
                    )

                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count
                )

                # 태스크 완료
                task_manager.complete_task(
                    task_id,
                    result=result_state.to_simple_dict()
                )

            except Exception as e:
                logger.error(f"시뮬레이션 준비 실패: {str(e)}")
                task_manager.fail_task(task_id, str(e))

                # 시뮬레이션 상태를 실패로 업데이트
                state = manager.get_simulation(simulation_id)
                if state:
                    state.status = SimulationStatus.FAILED
                    state.error = str(e)
                    manager._save_simulation_state(state)

        # 백그라운드 스레드 시작
        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "status": "preparing",
                "message": "준비 태스크가 시작되었습니다. /api/simulation/prepare/status 를 통해 진행 상황을 확인하세요",
                "already_prepared": False,
                "expected_entities_count": state.entities_count,  # 예상 Agent 총 수
                "entity_types": state.entity_types  # 엔티티 유형 목록
            }
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404

    except Exception as e:
        logger.error(f"준비 태스크 시작 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/prepare/status', methods=['POST'])
def get_prepare_status():
    """
    준비 태스크 진행 상황 조회

    두 가지 조회 방식 지원:
    1. task_id로 진행 중인 태스크 진행 상황 조회
    2. simulation_id로 완료된 준비 작업 여부 확인

    요청 (JSON):
        {
            "task_id": "task_xxxx",          // 선택적, prepare가 반환한 task_id
            "simulation_id": "sim_xxxx"      // 선택적, 시뮬레이션 ID (완료된 준비 확인용)
        }

    반환:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|ready",
                "progress": 45,
                "message": "...",
                "already_prepared": true|false,  // 이미 완료된 준비 작업 여부
                "prepare_info": {...}            // 준비 완료 시 상세 정보
            }
        }
    """
    from ..models.task import TaskManager

    try:
        data = request.get_json() or {}

        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')

        # simulation_id가 제공된 경우, 먼저 준비 완료 여부 확인
        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "이미 완료된 준비 작업이 있습니다",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })

        # task_id가 없으면 오류 반환
        if not task_id:
            if simulation_id:
                # simulation_id는 있지만 준비 미완료
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "not_started",
                        "progress": 0,
                        "message": "아직 준비가 시작되지 않았습니다. /api/simulation/prepare 를 호출하세요",
                        "already_prepared": False
                    }
                })
            return jsonify({
                "success": False,
                "error": "task_id 또는 simulation_id 를 제공해주세요"
            }), 400

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)

        if not task:
            # 태스크가 없지만 simulation_id가 있으면 준비 완료 여부 확인
            if simulation_id:
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": task_id,
                            "status": "ready",
                            "progress": 100,
                            "message": "태스크 완료 (준비 작업 이미 존재)",
                            "already_prepared": True,
                            "prepare_info": prepare_info
                        }
                    })

            return jsonify({
                "success": False,
                "error": f"태스크가 존재하지 않음: {task_id}"
            }), 404

        task_dict = task.to_dict()
        task_dict["already_prepared"] = False

        return jsonify({
            "success": True,
            "data": task_dict
        })

    except Exception as e:
        logger.error(f"태스크 상태 조회 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>', methods=['GET'])
def get_simulation(simulation_id: str):
    """시뮬레이션 상태 가져오기"""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"시뮬레이션이 존재하지 않음: {simulation_id}"
            }), 404

        result = state.to_dict()

        # 시뮬레이션이 준비 완료된 경우 실행 안내 첨부
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        logger.error(f"시뮬레이션 상태 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/list', methods=['GET'])
def list_simulations():
    """
    모든 시뮬레이션 목록 조회

    Query 파라미터:
        project_id: 프로젝트 ID로 필터링 (선택적)
    """
    try:
        project_id = request.args.get('project_id')

        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)

        return jsonify({
            "success": True,
            "data": [s.to_dict() for s in simulations],
            "count": len(simulations)
        })

    except Exception as e:
        logger.error(f"시뮬레이션 목록 조회 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/history', methods=['GET'])
def get_simulation_history():
    """
    히스토리 시뮬레이션 목록 조회 (프로젝트 상세 정보 포함)

    홈 화면 히스토리 프로젝트 표시에 사용, 프로젝트 이름, 설명 등 풍부한 정보를 포함한 시뮬레이션 목록 반환

    Query 파라미터:
        limit: 반환 수 제한 (기본값 20)

    반환:
        {
            "success": true,
            "data": [
                {
                    "simulation_id": "sim_xxxx",
                    "project_id": "proj_xxxx",
                    "project_name": "여론 분석",
                    "simulation_requirement": "만약 ...",
                    "status": "completed",
                    "entities_count": 68,
                    "profiles_count": 68,
                    "entity_types": ["Student", "Professor", ...],
                    "created_at": "2024-12-10",
                    "updated_at": "2024-12-10",
                    "total_rounds": 120,
                    "current_round": 120,
                    "report_id": "report_xxxx",
                    "version": "v1.0.2"
                },
                ...
            ],
            "count": 7
        }
    """
    try:
        limit = request.args.get('limit', 20, type=int)

        manager = SimulationManager()
        simulations = sorted(
            manager.list_simulations(),
            key=lambda s: s.created_at or '',
            reverse=True
        )[:limit]

        # 시뮬레이션 데이터 강화, Simulation 파일에서만 읽기
        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()

            # 시뮬레이션 설정 정보 가져오기 (simulation_config.json 에서 simulation_requirement 읽기)
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                # 권장 라운드 수 (후보 값)
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0) * 60 /
                    max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0

            # 실행 상태 가져오기 (run_state.json 에서 사용자가 설정한 실제 라운드 수 읽기)
            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                # 사용자가 설정한 total_rounds 사용, 없으면 권장 라운드 수 사용
                sim_dict["total_rounds"] = run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds

            # 연관 프로젝트 파일 목록 가져오기 (최대 3개)
            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, 'files') and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", "알 수 없는 파일")}
                    for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []

            # 연관된 report_id 가져오기 (해당 simulation 의 최신 report 검색)
            sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)

            # 버전 번호 추가
            sim_dict["version"] = "v1.0.2"

            # 날짜 포맷
            try:
                created_date = sim_dict.get("created_at", "")[:10]
                sim_dict["created_date"] = created_date
            except (TypeError, ValueError, AttributeError) as e:
                logger.warning(f"날짜 포맷 변환 실패: {e}")
                sim_dict["created_date"] = ""

            enriched_simulations.append(sim_dict)

        return jsonify({
            "success": True,
            "data": enriched_simulations,
            "count": len(enriched_simulations)
        })

    except Exception as e:
        logger.error(f"히스토리 시뮬레이션 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
def get_simulation_profiles(simulation_id: str):
    """
    시뮬레이션의 Agent Profile 가져오기

    Query 파라미터:
        platform: 플랫폼 유형 (reddit/twitter, 기본값 reddit)
    """
    try:
        platform = request.args.get('platform', 'reddit')
        
        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "profiles": profiles
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"Profile 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
def get_simulation_profiles_realtime(simulation_id: str):
    """
    시뮬레이션의 Agent Profile 실시간 가져오기 (생성 중 실시간 진행 상황 확인용)

    /profiles 인터페이스와의 차이:
    - SimulationManager를 거치지 않고 파일을 직접 읽음
    - 생성 중 실시간 확인에 적합
    - 추가 메타데이터 반환 (파일 수정 시간, 생성 중 여부 등)

    Query 파라미터:
        platform: 플랫폼 유형 (reddit/twitter, 기본값 reddit)

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "platform": "reddit",
                "count": 15,
                "total_expected": 93,  // 예상 총 수 (있는 경우)
                "is_generating": true,  // 생성 중 여부
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "profiles": [...]
            }
        }
    """
    import json
    import csv
    from datetime import datetime
    
    try:
        platform = request.args.get('platform', 'reddit')

        # 캐시 확인 (10초 TTL, 생성 중이 아닐 때만 유효)
        profiles_cache_key = f"profiles_realtime:{simulation_id}:{platform}"
        cached = entity_cache.get(profiles_cache_key)
        if cached is not None:
            logger.debug(f"캐시 히트: {profiles_cache_key}")
            return jsonify(cached)

        # 시뮬레이션 디렉토리 가져오기
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"시뮬레이션이 존재하지 않음: {simulation_id}"
            }), 404

        # 파일 경로 결정
        if platform == "reddit":
            profiles_file = os.path.join(sim_dir, "reddit_profiles.json")
        else:
            profiles_file = os.path.join(sim_dir, "twitter_profiles.csv")

        # 파일 존재 여부 확인
        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None

        if file_exists:
            # 파일 수정 시간 가져오기
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()

            try:
                if platform == "reddit":
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        profiles = json.load(f)
                else:
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        profiles = list(reader)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"profiles 파일 읽기 실패 (쓰기 중일 수 있음): {e}")
                profiles = []

        # 생성 중 여부 확인 (state.json 을 통해 판단)
        is_generating = False
        total_expected = None

        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    total_expected = state_data.get("entities_count")
            except Exception:
                pass

        response_data = {
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "platform": platform,
                "count": len(profiles),
                "total_expected": total_expected,
                "is_generating": is_generating,
                "file_exists": file_exists,
                "file_modified_at": file_modified_at,
                "profiles": profiles
            }
        }
        # 생성 중이 아닐 때만 캐시 저장 (10초 TTL)
        if not is_generating:
            entity_cache.set(profiles_cache_key, response_data, ttl=10)
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Profile 실시간 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== Profile 생성 인터페이스 (독립 사용) ==============

@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """
    그래프에서 직접 OASIS Agent Profile 생성 (시뮬레이션 생성 없이)

    요청 (JSON):
        {
            "graph_id": "mirofish_xxxx",     // 필수
            "entity_types": ["Student"],      // 선택적
            "use_llm": true,                  // 선택적
            "platform": "reddit"              // 선택적
        }
    """
    try:
        data = request.get_json() or {}

        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "graph_id 를 제공해주세요"
            }), 400

        entity_types = data.get('entity_types')
        use_llm = data.get('use_llm', True)
        platform = data.get('platform', 'reddit')

        reader = GraphitiEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True
        )

        if filtered.filtered_count == 0:
            return jsonify({
                "success": False,
                "error": "조건에 맞는 엔티티를 찾을 수 없습니다"
            }), 400
        
        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities,
            use_llm=use_llm
        )
        
        if platform == "reddit":
            profiles_data = [p.to_reddit_format() for p in profiles]
        elif platform == "twitter":
            profiles_data = [p.to_twitter_format() for p in profiles]
        else:
            profiles_data = [p.to_dict() for p in profiles]
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data
            }
        })
        
    except Exception as e:
        logger.error(f"Profile 생성 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== 시뮬레이션 실행 제어 인터페이스 ==============

@simulation_bp.route('/start', methods=['POST'])
def start_simulation():
    """
    시뮬레이션 실행 시작

    요청 (JSON):
        {
            "simulation_id": "sim_xxxx",          // 필수, 시뮬레이션 ID
            "platform": "parallel",                // 선택적: twitter / reddit / parallel (기본값)
            "max_rounds": 100,                     // 선택적: 최대 시뮬레이션 라운드 수, 너무 긴 시뮬레이션 중단용
            "enable_graph_memory_update": false,   // 선택적: Agent 활동을 Zep 그래프 메모리에 동적으로 업데이트할지 여부
            "force": false                         // 선택적: 강제 재시작 (실행 중인 시뮬레이션 중지 및 로그 정리)
        }

    force 파라미터 관련:
        - 활성화 시, 시뮬레이션이 실행 중이거나 완료된 경우 먼저 중지 후 실행 로그 정리
        - 정리 내용: run_state.json, actions.jsonl, simulation.log 등
        - 설정 파일 (simulation_config.json) 및 profile 파일은 정리하지 않음
        - 시뮬레이션을 재실행해야 하는 경우에 사용

    enable_graph_memory_update 관련:
        - 활성화 시, 시뮬레이션의 모든 Agent 활동 (게시, 댓글, 좋아요 등) 이 Zep 그래프에 실시간 업데이트됨
        - 그래프가 시뮬레이션 과정을 "기억"하여 이후 분석 또는 AI 대화에 활용 가능
        - 시뮬레이션과 연결된 프로젝트에 유효한 graph_id 가 있어야 함
        - 배치 업데이트 메커니즘을 사용하여 API 호출 횟수 절감

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,  // 그래프 메모리 업데이트 활성화 여부
                "force_restarted": true               // 강제 재시작 여부
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id 를 제공해주세요"
            }), 400

        platform = data.get('platform', 'parallel')
        max_rounds = data.get('max_rounds')  # 선택적: 최대 시뮬레이션 라운드 수
        enable_graph_memory_update = data.get('enable_graph_memory_update', False)  # 선택적: 그래프 메모리 업데이트 활성화 여부
        force = data.get('force', False)  # 선택적: 강제 재시작

        # max_rounds 파라미터 검증
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({
                        "success": False,
                        "error": "max_rounds 는 양의 정수여야 합니다"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": "max_rounds 는 유효한 정수여야 합니다"
                }), 400

        if platform not in ['twitter', 'reddit', 'parallel']:
            return jsonify({
                "success": False,
                "error": f"유효하지 않은 플랫폼 유형: {platform}, 선택 가능: twitter/reddit/parallel"
            }), 400

        # 시뮬레이션 준비 완료 여부 확인
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"시뮬레이션이 존재하지 않음: {simulation_id}"
            }), 404

        force_restarted = False

        # 상태 지능적 처리: 준비 작업이 완료된 경우 재시작 허용
        if state.status != SimulationStatus.READY:
            # 준비 작업 완료 여부 확인
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # 준비 완료, 실행 중인 프로세스 있는지 확인
                if state.status == SimulationStatus.RUNNING:
                    # 시뮬레이션 프로세스가 실제로 실행 중인지 확인
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # 프로세스가 실제로 실행 중
                        if force:
                            # 강제 모드: 실행 중인 시뮬레이션 중지
                            logger.info(f"강제 모드: 실행 중인 시뮬레이션 중지 {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"시뮬레이션 중지 시 경고: {str(e)}")
                        else:
                            return jsonify({
                                "success": False,
                                "error": f"시뮬레이션이 실행 중입니다. 먼저 /stop 인터페이스를 호출하여 중지하거나 force=true 를 사용해 강제 재시작하세요"
                            }), 400

                # 강제 모드인 경우 실행 로그 정리
                if force:
                    logger.info(f"강제 모드: 시뮬레이션 로그 정리 {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"로그 정리 시 경고: {cleanup_result.get('errors')}")
                    force_restarted = True

                # 프로세스가 없거나 이미 종료됨, 상태를 ready 로 재설정
                logger.info(f"시뮬레이션 {simulation_id} 준비 작업 완료, 상태를 ready 로 재설정 (기존 상태: {state.status.value})")
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # 준비 작업 미완료
                return jsonify({
                    "success": False,
                    "error": f"시뮬레이션이 준비되지 않았습니다. 현재 상태: {state.status.value}, 먼저 /prepare 인터페이스를 호출해주세요"
                }), 400

        # 그래프 ID 가져오기 (그래프 메모리 업데이트용)
        graph_id = None
        if enable_graph_memory_update:
            # 시뮬레이션 상태 또는 프로젝트에서 graph_id 가져오기
            graph_id = state.graph_id
            if not graph_id:
                # 프로젝트에서 가져오기 시도
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id

            if not graph_id:
                return jsonify({
                    "success": False,
                    "error": "그래프 메모리 업데이트를 활성화하려면 유효한 graph_id 가 필요합니다. 프로젝트에 그래프가 구축되었는지 확인하세요"
                }), 400

            logger.info(f"그래프 메모리 업데이트 활성화: simulation_id={simulation_id}, graph_id={graph_id}")
        
        # 시뮬레이션 시작
        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id
        )

        # 시뮬레이션 상태 업데이트
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        
        response_data = run_state.to_dict()
        if max_rounds:
            response_data['max_rounds_applied'] = max_rounds
        response_data['graph_memory_update_enabled'] = enable_graph_memory_update
        response_data['force_restarted'] = force_restarted
        if enable_graph_memory_update:
            response_data['graph_id'] = graph_id
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except SimulationLimitError as e:
        logger.warning(f"동시 시뮬레이션 제한 초과: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 429

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except Exception as e:
        logger.error(f"시뮬레이션 시작 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/stop', methods=['POST'])
def stop_simulation():
    """
    시뮬레이션 중지

    요청 (JSON):
        {
            "simulation_id": "sim_xxxx"  // 필수, 시뮬레이션 ID
        }

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id 를 제공해주세요"
            }), 400

        run_state = SimulationRunner.stop_simulation(simulation_id)

        # 시뮬레이션 상태 업데이트
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)

        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except Exception as e:
        logger.error(f"시뮬레이션 중지 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== 실시간 상태 모니터링 인터페이스 ==============

@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
def get_run_status(simulation_id: str):
    """
    시뮬레이션 실행 실시간 상태 가져오기 (프론트엔드 폴링용)

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                "total_rounds": 144,
                "progress_percent": 3.5,
                "simulated_hours": 2,
                "total_simulation_hours": 72,
                "twitter_running": true,
                "reddit_running": true,
                "twitter_actions_count": 150,
                "reddit_actions_count": 200,
                "total_actions_count": 350,
                "started_at": "2025-12-01T10:00:00",
                "updated_at": "2025-12-01T10:30:00"
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percent": 0,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                }
            })
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except Exception as e:
        logger.error(f"실행 상태 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
def get_run_status_detail(simulation_id: str):
    """
    시뮬레이션 실행 상세 상태 가져오기 (모든 액션 포함)

    프론트엔드 실시간 동적 표시에 사용

    Query 파라미터:
        platform: 플랫폼 필터링 (twitter/reddit, 선택적)

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                ...
                "all_actions": [
                    {
                        "round_num": 5,
                        "timestamp": "2025-12-01T10:30:00",
                        "platform": "twitter",
                        "agent_id": 3,
                        "agent_name": "Agent Name",
                        "action_type": "CREATE_POST",
                        "action_args": {"content": "..."},
                        "result": null,
                        "success": true
                    },
                    ...
                ],
                "twitter_actions": [...],  # Twitter 플랫폼의 모든 액션
                "reddit_actions": [...]    # Reddit 플랫폼의 모든 액션
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get('platform')
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "all_actions": [],
                    "twitter_actions": [],
                    "reddit_actions": []
                }
            })
        
        # 전체 액션 목록 가져오기
        all_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter
        )

        # 플랫폼별 액션 가져오기
        twitter_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="twitter"
        ) if not platform_filter or platform_filter == "twitter" else []
        
        reddit_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="reddit"
        ) if not platform_filter or platform_filter == "reddit" else []
        
        # 현재 라운드의 액션 가져오기 (recent_actions 는 최신 라운드만 표시)
        current_round = run_state.current_round
        recent_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter,
            round_num=current_round
        ) if current_round > 0 else []
        
        # 기본 상태 정보 가져오기
        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["twitter_actions"] = [a.to_dict() for a in twitter_actions]
        result["reddit_actions"] = [a.to_dict() for a in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        # recent_actions 는 현재 최신 라운드의 두 플랫폼 내용만 표시
        result["recent_actions"] = [a.to_dict() for a in recent_actions]
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"상세 상태 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/env-status', methods=['POST'])
def get_env_status():
    """
    시뮬레이션 환경 상태 가져오기

    시뮬레이션 환경 생존 여부 확인 (Interview 명령 수신 가능 여부)

    요청 (JSON):
        {
            "simulation_id": "sim_xxxx"  // 필수, 시뮬레이션 ID
        }

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "env_alive": true,
                "twitter_available": true,
                "reddit_available": true,
                "message": "환경이 실행 중이며 Interview 명령을 수신할 수 있습니다"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id 를 제공해주세요"
            }), 400

        env_alive = SimulationRunner.check_env_alive(simulation_id)

        # 더 상세한 상태 정보 가져오기
        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = "환경이 실행 중이며 Interview 명령을 수신할 수 있습니다"
        else:
            message = "환경이 실행 중이 아니거나 종료되었습니다"

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "env_alive": env_alive,
                "twitter_available": env_status.get("twitter_available", False),
                "reddit_available": env_status.get("reddit_available", False),
                "message": message
            }
        })

    except Exception as e:
        logger.error(f"환경 상태 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/close-env', methods=['POST'])
def close_simulation_env():
    """
    시뮬레이션 환경 종료

    시뮬레이션에 환경 종료 명령을 전송하여 명령 대기 모드에서 우아하게 종료.

    참고: /stop 인터페이스와 다름. /stop 은 프로세스를 강제 종료하지만,
    이 인터페이스는 시뮬레이션이 환경을 우아하게 종료하고 종료하도록 함.

    요청 (JSON):
        {
            "simulation_id": "sim_xxxx",  // 필수, 시뮬레이션 ID
            "timeout": 30                  // 선택적, 타임아웃 시간 (초), 기본값 30
        }

    반환:
        {
            "success": true,
            "data": {
                "message": "환경 종료 명령이 전송되었습니다",
                "result": {...},
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        timeout = data.get('timeout', 30)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id 를 제공해주세요"
            }), 400
        
        result = SimulationRunner.close_simulation_env(
            simulation_id=simulation_id,
            timeout=timeout
        )
        
        # 시뮬레이션 상태 업데이트
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"환경 종료 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
