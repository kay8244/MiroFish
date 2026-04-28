"""
시뮬레이션 - 엔티티 읽기 인터페이스

Graphiti 그래프에서 정의된 엔티티 유형을 필터링하여 조회.
"""

import traceback

from flask import jsonify, request

from .. import simulation_bp
from ...services.graphiti_entity_reader import GraphitiEntityReader
from ...utils.cache import entity_cache
from ...utils.logger import get_logger

logger = get_logger('mirofish.api.simulation')


@simulation_bp.route('/entities/<graph_id>', methods=['GET'])
def get_graph_entities(graph_id: str):
    """
    그래프의 모든 엔티티 가져오기 (필터링 적용)

    사전 정의된 엔티티 유형에 맞는 노드만 반환 (Labels가 Entity만이 아닌 노드)

    Query 파라미터:
        entity_types: 쉼표로 구분된 엔티티 유형 목록 (선택적, 추가 필터링용)
        enrich: 관련 엣지 정보 가져오기 여부 (기본값 true)
    """
    try:
        # graph_id 검증
        if not graph_id or not graph_id.strip():
            return jsonify({
                "success": False,
                "error": "graph_id 를 제공해주세요"
            }), 400

        entity_types_str = request.args.get('entity_types', '')
        entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()] if entity_types_str else None
        enrich = request.args.get('enrich', 'true').lower() == 'true'

        # 캐시 키: graph_id + 필터 파라미터 조합
        cache_key = f"entities:{graph_id}:{entity_types_str}:{enrich}"
        cached = entity_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"캐시 히트: {cache_key}")
            return jsonify(cached)

        logger.info(f"그래프 엔티티 가져오기: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}")

        reader = GraphitiEntityReader()
        result = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=enrich
        )

        response_data = {
            "success": True,
            "data": result.to_dict()
        }
        entity_cache.set(cache_key, response_data, ttl=60)
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"그래프 엔티티 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """단일 엔티티 상세 정보 가져오기"""
    try:
        reader = GraphitiEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)

        if not entity:
            return jsonify({
                "success": False,
                "error": f"엔티티가 존재하지 않음: {entity_uuid}"
            }), 404

        return jsonify({
            "success": True,
            "data": entity.to_dict()
        })

    except Exception as e:
        logger.error(f"엔티티 상세 정보 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type(graph_id: str, entity_type: str):
    """지정된 유형의 모든 엔티티 가져오기"""
    try:
        enrich = request.args.get('enrich', 'true').lower() == 'true'

        reader = GraphitiEntityReader()
        entities = reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich
        )

        return jsonify({
            "success": True,
            "data": {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": [e.to_dict() for e in entities]
            }
        })

    except Exception as e:
        logger.error(f"엔티티 가져오기 실패: {str(e)}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
