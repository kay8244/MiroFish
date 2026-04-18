"""
간단한 인메모리 TTL 캐시
외부 의존성 없이 동작하는 경량 구현
"""

import time
import threading
from ..utils.logger import get_logger

logger = get_logger('mirofish.cache')


class SimpleCache:
    """TTL 기반 인메모리 캐시"""

    def __init__(self, default_ttl: int = 60):
        self._store: dict = {}  # key -> (value, expire_time)
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def get(self, key: str):
        """캐시에서 값 조회. 만료되었으면 None 반환"""
        with self._lock:
            if key in self._store:
                value, expire_time = self._store[key]
                if time.time() < expire_time:
                    return value
                del self._store[key]
            return None

    def set(self, key: str, value, ttl: int | None = None) -> None:
        """캐시에 값 저장"""
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._store[key] = (value, time.time() + ttl)

    def invalidate(self, key: str) -> None:
        """캐시 항목 삭제"""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """전체 캐시 초기화"""
        with self._lock:
            self._store.clear()


# 글로벌 인스턴스 (60초 TTL)
entity_cache = SimpleCache(default_ttl=60)
