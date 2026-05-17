"""
Retry Mechanism with Exponential Backoff

提供:
- 工具重试装饰器
- 指数退避策略
- 重试配置
- 预算感知重试
"""
import asyncio
import logging
import time
from typing import Callable, Any, Optional
from dataclasses import dataclass
from functools import wraps

from .schemas import (
    ErrorEnvelope,
    ErrorType,
    ErrorLevel,
    StructuredAgentError,
    ERROR_CODES,
)

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    retry_on_exceptions: tuple = (Exception,)


# Per-component retry configurations (aligned with agent-flow-design.md)
LLMRetryConfig = RetryConfig(
    max_retries=3,
    initial_delay=1.0,
    backoff_factor=2.0,
)
ToolRetryConfig = RetryConfig(
    max_retries=3,
    initial_delay=0.5,
    backoff_factor=2.0,
)
SupervisorRetryConfig = RetryConfig(
    max_retries=2,
    initial_delay=1.0,
    backoff_factor=2.0,
)


def retry_with_backoff(config: RetryConfig = None):
    """重试装饰器 - 指数退避"""
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            delay = config.initial_delay
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except config.retry_on_exceptions as e:
                    last_exception = e
                    if attempt < config.max_retries:
                        logger.warning(
                            f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{config.max_retries + 1}): {e}"
                        )
                        time.sleep(delay)
                        delay = min(delay * config.backoff_factor, config.max_delay)
                    else:
                        logger.error(f"[Retry] {func.__name__} failed after {config.max_retries + 1} attempts")

            raise last_exception

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            delay = config.initial_delay
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except config.retry_on_exceptions as e:
                    last_exception = e
                    if attempt < config.max_retries:
                        logger.warning(
                            f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{config.max_retries + 1}): {e}"
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * config.backoff_factor, config.max_delay)
                    else:
                        logger.error(f"[Retry] {func.__name__} failed after {config.max_retries + 1} attempts")

            raise last_exception

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class RetryableTool:
    """可重试工具包装器"""

    def __init__(self, tool_func: Callable, config: RetryConfig = None):
        self.tool_func = tool_func
        self.config = config or RetryConfig()

    def invoke(self, tool_input: dict) -> Any:
        return retry_with_backoff(self.config)(self.tool_func)(tool_input)

    async def ainvoke(self, tool_input: dict) -> Any:
        return await retry_with_backoff(self.config)(self.tool_func)(tool_input)


class RetryManager:
    """重试管理器"""

    def __init__(self):
        self._retry_counts: dict[str, int] = {}
        self._total_retries: int = 0

    def record_retry(self, operation: str):
        self._retry_counts[operation] = self._retry_counts.get(operation, 0) + 1
        self._total_retries += 1

    def get_stats(self) -> dict:
        return {
            "total_retries": self._total_retries,
            "by_operation": dict(self._retry_counts),
        }

    def reset(self):
        self._retry_counts.clear()
        self._total_retries = 0


def retry_with_budget(
    max_retries: int = 2,
    estimated_retry_cost: float = 0.001,
    circuit_breaker=None,
):
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            remaining = kwargs.get("_remaining_budget")
            if remaining is not None and remaining < estimated_retry_cost:
                raise StructuredAgentError(
                    error_code="BUDGET_EXHAUSTED",
                    error_type=ErrorType.FATAL,
                    message=f"预算不足 ({remaining} < {estimated_retry_cost})",
                    retryable=False,
                    error_level=ErrorLevel.CRITICAL,
                )
            if circuit_breaker and not circuit_breaker.can_execute():
                raise StructuredAgentError(
                    error_code="CIRCUIT_BREAKER_OPEN",
                    error_type=ErrorType.RECOVERABLE,
                    message="熔断器开启，跳过执行",
                    retryable=True,
                    error_level=ErrorLevel.HIGH,
                )
            return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            remaining = kwargs.get("_remaining_budget")
            if remaining is not None and remaining < estimated_retry_cost:
                raise StructuredAgentError(
                    error_code="BUDGET_EXHAUSTED",
                    error_type=ErrorType.FATAL,
                    message=f"预算不足 ({remaining} < {estimated_retry_cost})",
                    retryable=False,
                    error_level=ErrorLevel.CRITICAL,
                )
            if circuit_breaker and not circuit_breaker.can_execute():
                raise StructuredAgentError(
                    error_code="CIRCUIT_BREAKER_OPEN",
                    error_type=ErrorType.RECOVERABLE,
                    message="熔断器开启，跳过执行",
                    retryable=True,
                    error_level=ErrorLevel.HIGH,
                )
            return await func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


_retry_manager: Optional[RetryManager] = None


def get_retry_manager() -> RetryManager:
    global _retry_manager
    if _retry_manager is None:
        _retry_manager = RetryManager()
    return _retry_manager