"""
중앙 집중식 API 에러 핸들러
모든 API 엔드포인트에서 공통으로 사용하는 에러 처리 데코레이터
"""

import traceback
from functools import wraps
from flask import jsonify
from ..utils.logger import get_logger

logger = get_logger('mirofish.api')


def api_error_handler(f):
    """
    API 엔드포인트 에러 핸들러 데코레이터

    표준화된 에러 응답 형식:
    {"success": false, "error": "<message>", "code": "<error_code>"}
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"잘못된 요청 ({f.__name__}): {str(e)}")
            logger.debug(traceback.format_exc())
            return jsonify({
                "success": False,
                "error": str(e),
                "code": "INVALID_REQUEST"
            }), 400
        except FileNotFoundError as e:
            logger.warning(f"리소스 없음 ({f.__name__}): {str(e)}")
            logger.debug(traceback.format_exc())
            return jsonify({
                "success": False,
                "error": str(e),
                "code": "NOT_FOUND"
            }), 404
        except Exception as e:
            logger.error(f"서버 오류 ({f.__name__}): {str(e)}")
            logger.debug(traceback.format_exc())
            return jsonify({
                "success": False,
                "error": str(e),
                "code": "INTERNAL_ERROR"
            }), 500
    return wrapper
