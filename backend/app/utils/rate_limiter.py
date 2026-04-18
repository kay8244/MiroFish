"""
간단한 인메모리 API 속도 제한기
외부 의존성 없이 동작하는 경량 구현
"""

import time
import threading
from functools import wraps
from flask import request, jsonify
from ..utils.logger import get_logger

logger = get_logger('mirofish.rate_limiter')


class SimpleRateLimiter:
    """토큰 버킷 기반 인메모리 속도 제한기"""

    def __init__(self):
        self._buckets = {}  # key -> (tokens, last_refill_time)
        self._lock = threading.Lock()

    def _get_key(self, identifier, endpoint):
        return f"{identifier}:{endpoint}"

    def is_allowed(self, identifier, endpoint, max_requests, period_seconds):
        """요청 허용 여부 확인"""
        key = self._get_key(identifier, endpoint)
        now = time.time()

        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = (max_requests - 1, now)
                return True

            tokens, last_time = self._buckets[key]
            elapsed = now - last_time

            # 토큰 리필
            refill = elapsed * (max_requests / period_seconds)
            tokens = min(max_requests, tokens + refill)

            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return True

            self._buckets[key] = (tokens, now)
            return False


# 글로벌 인스턴스
_limiter = SimpleRateLimiter()


def rate_limit(max_requests=5, period_seconds=60):
    """
    속도 제한 데코레이터

    Args:
        max_requests: 기간 내 최대 요청 수
        period_seconds: 기간 (초)
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            identifier = request.remote_addr or 'unknown'
            endpoint = request.endpoint or f.__name__

            if not _limiter.is_allowed(identifier, endpoint, max_requests, period_seconds):
                logger.warning(f"속도 제한 초과: {identifier} -> {endpoint}")
                return jsonify({
                    "success": False,
                    "error": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
                }), 429

            return f(*args, **kwargs)
        return wrapper
    return decorator
