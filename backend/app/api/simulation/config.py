"""
시뮬레이션 - 설정·다운로드 인터페이스

LLM이 생성한 simulation_config.json 의 조회·실시간 진행 상황·다운로드
+ 공통 실행 스크립트 다운로드.
"""

import json
import os
import traceback
from datetime import datetime

from flask import jsonify, send_file

from .. import simulation_bp
from ...config import Config
from ...services.simulation_manager import SimulationManager
from ...utils.logger import get_logger
from ._shared import BACKEND_DIR

logger = get_logger('mirofish.api.simulation')


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
def get_simulation_config_realtime(simulation_id: str):
    """
    시뮬레이션 설정 실시간 가져오기 (생성 중 실시간 진행 상황 확인용)

    /config 인터페이스와의 차이:
    - SimulationManager를 거치지 않고 파일을 직접 읽음
    - 생성 중 실시간 확인에 적합
    - 추가 메타데이터 반환 (파일 수정 시간, 생성 중 여부 등)
    - 설정이 아직 생성 완료되지 않아도 일부 정보 반환 가능

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "is_generating": true,  // 생성 중 여부
                "generation_stage": "generating_config",  // 현재 생성 단계
                "config": {...}  // 설정 내용 (존재하는 경우)
            }
        }
    """
    try:
        # 시뮬레이션 디렉토리 가져오기
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": f"시뮬레이션이 존재하지 않음: {simulation_id}"
            }), 404

        # 설정 파일 경로
        config_file = os.path.join(sim_dir, "simulation_config.json")

        # 파일 존재 여부 확인
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None

        if file_exists:
            # 파일 수정 시간 가져오기
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()

            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"config 파일 읽기 실패 (쓰기 중일 수 있음): {e}")
                config = None

        # 생성 중 여부 확인 (state.json 을 통해 판단)
        is_generating = False
        generation_stage = None
        config_generated = False

        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    config_generated = state_data.get("config_generated", False)

                    # 현재 단계 판단
                    if is_generating:
                        if state_data.get("profiles_generated", False):
                            generation_stage = "generating_config"
                        else:
                            generation_stage = "generating_profiles"
                    elif status == "ready":
                        generation_stage = "completed"
            except Exception:
                pass

        # 반환 데이터 구성
        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "config": config
        }

        # 설정이 존재하는 경우 주요 통계 정보 추출
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model")
            }

        return jsonify({
            "success": True,
            "data": response_data
        })

    except Exception as e:
        logger.error(f"Config 실시간 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>/config', methods=['GET'])
def get_simulation_config(simulation_id: str):
    """
    시뮬레이션 설정 가져오기 (LLM이 지능적으로 생성한 완전한 설정)

    반환 내용:
        - time_config: 시간 설정 (시뮬레이션 기간, 라운드, 피크/저조 시간대)
        - agent_configs: 각 Agent의 활동 설정 (활성도, 발언 빈도, 입장 등)
        - event_config: 이벤트 설정 (초기 게시물, 핫 토픽)
        - platform_configs: 플랫폼 설정
        - generation_reasoning: LLM의 설정 추론 설명
    """
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)

        if not config:
            return jsonify({
                "success": False,
                "error": "시뮬레이션 설정이 없습니다. 먼저 /prepare 인터페이스를 호출해주세요"
            }), 404

        return jsonify({
            "success": True,
            "data": config
        })

    except Exception as e:
        logger.error(f"설정 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
def download_simulation_config(simulation_id: str):
    """시뮬레이션 설정 파일 다운로드"""
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")

        if not os.path.exists(config_path):
            return jsonify({
                "success": False,
                "error": "설정 파일이 없습니다. 먼저 /prepare 인터페이스를 호출해주세요"
            }), 404

        return send_file(
            config_path,
            as_attachment=True,
            download_name="simulation_config.json"
        )

    except Exception as e:
        logger.error(f"설정 다운로드 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
def download_simulation_script(script_name: str):
    """
    시뮬레이션 실행 스크립트 파일 다운로드 (공통 스크립트, backend/scripts/ 에 위치)

    script_name 선택 가능 값:
        - run_twitter_simulation.py
        - run_reddit_simulation.py
        - run_parallel_simulation.py
        - action_logger.py
    """
    try:
        # 스크립트는 backend/scripts/ 디렉토리에 위치
        scripts_dir = os.path.join(BACKEND_DIR, 'scripts')

        # 스크립트 이름 검증
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py",
            "run_parallel_simulation.py",
            "action_logger.py"
        ]

        if script_name not in allowed_scripts:
            return jsonify({
                "success": False,
                "error": f"알 수 없는 스크립트: {script_name}, 선택 가능: {allowed_scripts}"
            }), 400

        script_path = os.path.join(scripts_dir, script_name)

        if not os.path.exists(script_path):
            return jsonify({
                "success": False,
                "error": f"스크립트 파일이 존재하지 않음: {script_name}"
            }), 404

        return send_file(
            script_path,
            as_attachment=True,
            download_name=script_name
        )

    except Exception as e:
        logger.error(f"스크립트 다운로드 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
