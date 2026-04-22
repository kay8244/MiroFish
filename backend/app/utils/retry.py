"""
API 호출 재시도 메커니즘
LLM 등 외부 API 호출의 재시도 로직 처리에 사용
"""

import time
import random
import functools
from typing import Callable, Any, Optional, Type, Tuple
from ..utils.logger import get_logger

logger = get_logger('mirofish.retry')


# Fix E: quota/auth 에러는 재시도해도 해결되지 않으므로 fail-fast.
# 에러 메시지에 아래 패턴이 포함되면 즉시 raise (재시도 X).
NON_RETRYABLE_PATTERNS: Tuple[str, ...] = (
    'insufficient_quota',
    'quota_exceeded',
    'invalid_api_key',
    'authentication_error',
    'incorrect_api_key',
    'account_deactivated',
    'billing_not_active',
    'permission_denied',
)


def _is_non_retryable(exc: BaseException) -> bool:
    """에러 메시지가 non-retryable 패턴(quota/auth)을 포함하는지 검사.

    LLM provider별로 에러 메시지 포맷이 다르지만 'insufficient_quota',
    'invalid_api_key' 같은 공통 토큰을 match해서 조기 중단.
    """
    msg = str(exc).lower()
    return any(p in msg for p in NON_RETRYABLE_PATTERNS)


# Fix G2: rate_limit_error 는 분당 한도라 짧은 backoff (2-8s) 로는 회복 불가.
# 60초 기다려야 다음 분 윈도우에서 한도 갱신됨. 패턴 매치 시 강제 60s 대기.
RATE_LIMIT_PATTERNS: Tuple[str, ...] = (
    'rate_limit_error',
    'rate_limit_exceeded',
    'rate limit exceeded',
    'tokens per minute',
    'requests per minute',
    'tpm',
    'rpm',
)
RATE_LIMIT_BACKOFF_S: float = 65.0  # Anthropic per-minute window 1바퀴 + 마진 5s


def _is_rate_limit(exc: BaseException) -> bool:
    """rate_limit 에러 (분당 토큰/요청 한도 초과) 인지 검사."""
    msg = str(exc).lower()
    return any(p in msg for p in RATE_LIMIT_PATTERNS)


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    지수 백오프를 사용하는 재시도 데코레이터

    Args:
        max_retries: 최대 재시도 횟수
        initial_delay: 초기 지연 시간（초）
        max_delay: 최대 지연 시간（초）
        backoff_factor: 백오프 계수
        jitter: 무작위 지터 추가 여부
        exceptions: 재시도할 예외 유형
        on_retry: 재시도 시 콜백 함수 (exception, retry_count)

    Usage:
        @retry_with_backoff(max_retries=3)
        def call_llm_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    # Fix E: quota/auth 에러는 재시도 무의미 → fail-fast
                    if _is_non_retryable(e):
                        logger.error(
                            f"함수 {func.__name__}: 재시도 불가 에러 (quota/auth) → 즉시 실패: {str(e)}"
                        )
                        raise

                    if attempt == max_retries:
                        logger.error(f"함수 {func.__name__} 이(가) {max_retries}번 재시도 후에도 실패: {str(e)}")
                        raise

                    # Fix G2: rate_limit 은 분당 윈도우 → 강제 60s+ backoff
                    if _is_rate_limit(e):
                        current_delay = RATE_LIMIT_BACKOFF_S
                        logger.warning(
                            f"함수 {func.__name__} rate_limit 감지 (시도 {attempt + 1}): "
                            f"{current_delay:.0f}초 대기 (분당 윈도우 회복)..."
                        )
                    else:
                        # 일반 backoff
                        current_delay = min(delay, max_delay)
                        if jitter:
                            current_delay = current_delay * (0.5 + random.random())
                        logger.warning(
                            f"함수 {func.__name__} 의 {attempt + 1}번째 시도 실패: {str(e)}, "
                            f"{current_delay:.1f}초 후 재시도..."
                        )

                    if on_retry:
                        on_retry(e, attempt + 1)

                    time.sleep(current_delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper
    return decorator


def retry_with_backoff_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    비동기 버전의 재시도 데코레이터
    """
    import asyncio

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    # Fix E: quota/auth 에러는 재시도 무의미 → fail-fast
                    if _is_non_retryable(e):
                        logger.error(
                            f"비동기 함수 {func.__name__}: 재시도 불가 에러 (quota/auth) → 즉시 실패: {str(e)}"
                        )
                        raise

                    if attempt == max_retries:
                        logger.error(f"비동기 함수 {func.__name__} 이(가) {max_retries}번 재시도 후에도 실패: {str(e)}")
                        raise

                    # Fix G2: rate_limit 강제 long backoff (60s+)
                    if _is_rate_limit(e):
                        current_delay = RATE_LIMIT_BACKOFF_S
                        logger.warning(
                            f"비동기 함수 {func.__name__} rate_limit 감지 (시도 {attempt + 1}): "
                            f"{current_delay:.0f}초 대기..."
                        )
                        if on_retry:
                            on_retry(e, attempt + 1)
                        await asyncio.sleep(current_delay)
                        delay *= backoff_factor
                        continue

                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())

                    logger.warning(
                        f"비동기 함수 {func.__name__} 의 {attempt + 1}번째 시도 실패: {str(e)}, "
                        f"{current_delay:.1f}초 후 재시도..."
                    )

                    if on_retry:
                        on_retry(e, attempt + 1)

                    await asyncio.sleep(current_delay)
                    delay *= backoff_factor

            raise last_exception

        return wrapper
    return decorator


class RetryableAPIClient:
    """
    재시도 가능한 API 클라이언트 래퍼
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def call_with_retry(
        self,
        func: Callable,
        *args,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        **kwargs
    ) -> Any:
        """
        함수 호출 실행 및 실패 시 재시도

        Args:
            func: 호출할 함수
            *args: 함수 인수
            exceptions: 재시도할 예외 유형
            **kwargs: 함수 키워드 인수

        Returns:
            함수 반환값
        """
        last_exception = None
        delay = self.initial_delay

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)

            except exceptions as e:
                last_exception = e

                if attempt == self.max_retries:
                    logger.error(f"API 호출이 {self.max_retries}번 재시도 후에도 실패: {str(e)}")
                    raise

                current_delay = min(delay, self.max_delay)
                current_delay = current_delay * (0.5 + random.random())

                logger.warning(
                    f"API 호출 {attempt + 1}번째 시도 실패: {str(e)}, "
                    f"{current_delay:.1f}초 후 재시도..."
                )

                time.sleep(current_delay)
                delay *= self.backoff_factor

        raise last_exception

    def call_batch_with_retry(
        self,
        items: list,
        process_func: Callable,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        continue_on_failure: bool = True
    ) -> Tuple[list, list]:
        """
        일괄 호출 및 각 실패 항목에 대한 개별 재시도

        Args:
            items: 처리할 항목 목록
            process_func: 처리 함수, 단일 item을 인수로 받음
            exceptions: 재시도할 예외 유형
            continue_on_failure: 단일 항목 실패 후 다른 항목 계속 처리 여부

        Returns:
            (성공 결과 목록, 실패 항목 목록)
        """
        results = []
        failures = []

        for idx, item in enumerate(items):
            try:
                result = self.call_with_retry(
                    process_func,
                    item,
                    exceptions=exceptions
                )
                results.append(result)

            except Exception as e:
                logger.error(f"{idx + 1}번째 항목 처리 실패: {str(e)}")
                failures.append({
                    "index": idx,
                    "item": item,
                    "error": str(e)
                })

                if not continue_on_failure:
                    raise

        return results, failures

