"""
시뮬레이션 - 관리(CRUD) 인터페이스

시뮬레이션 자체의 생애주기 메타데이터: 생성·환경 준비(비동기 태스크)·
준비 진행 상황·단건/목록/히스토리 조회.
"""

import threading
import traceback

from flask import jsonify, request

from .. import simulation_bp
from ...models.project import ProjectManager
from ...models.task import TaskManager, TaskStatus
from ...services.graphiti_entity_reader import GraphitiEntityReader
from ...services.simulation_manager import SimulationManager, SimulationStatus
from ...services.simulation_runner import SimulationRunner
from ...utils.logger import get_logger
from ...utils.rate_limiter import rate_limit
from ._shared import _check_simulation_prepared, _get_report_id_for_simulation

logger = get_logger('mirofish.api.simulation')


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
