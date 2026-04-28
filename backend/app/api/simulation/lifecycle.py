"""
시뮬레이션 - 실행 제어·상태 모니터링 인터페이스

시뮬레이션 시작·중지·실시간 상태 폴링·환경 생존 여부 확인·환경 우아하게
종료. 시뮬레이션의 라이프사이클 전반을 다룬다.
"""

import traceback

from flask import jsonify, request

from .. import simulation_bp
from ...models.project import ProjectManager
from ...services.simulation_manager import SimulationManager, SimulationStatus
from ...services.simulation_runner import SimulationLimitError, SimulationRunner
from ...utils.logger import get_logger
from ._shared import _check_simulation_prepared

logger = get_logger('mirofish.api.simulation')


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
