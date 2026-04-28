"""
시뮬레이션 - Agent Profile 인터페이스

시뮬레이션의 Agent profile 조회 (manager 경유 / 파일 직접 실시간) +
독립 profile 생성 (시뮬레이션 생성 없이 그래프에서 직접).
"""

import csv
import json
import os
import traceback
from datetime import datetime

from flask import jsonify, request

from .. import simulation_bp
from ...config import Config
from ...services.graphiti_entity_reader import GraphitiEntityReader
from ...services.oasis_profile_generator import OasisProfileGenerator
from ...services.simulation_manager import SimulationManager
from ...utils.cache import entity_cache
from ...utils.logger import get_logger

logger = get_logger('mirofish.api.simulation')


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
