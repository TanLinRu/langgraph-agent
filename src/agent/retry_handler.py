"""
Retry Mechanism with Exponential Backoff

提供:
- 工具重试装饰器
- 指数退避策略
- 重试配置
"""
import asyncio
import logging
import time
from typing import Callable, Any, Optional
from dataclasses import dataclass
from functools import wraps

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    retry_on_exceptions: tuple = (Exception,)


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


_retry_manager: Optional[RetryManager] = None


def get_retry_manager() -> RetryManager:
    global _retry_manager
    if _retry_manager is None:
        _retry_manager = RetryManager()
    return _retry_manager