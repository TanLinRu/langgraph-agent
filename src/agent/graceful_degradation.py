"""
Graceful Degradation

提供:
- 服务降级处理
- 降级策略
- 回退响应
"""
import logging
from typing import Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class DegradationLevel(Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    FAILURE = "failure"


@dataclass
class DegradationConfig:
    enable_llm_fallback: bool = True
    enable_vector_fallback: bool = True
    enable_partial_results: bool = True
    max_retries_before_degradation: int = 2


class GracefulDegradation:
    """优雅降级处理器"""

    def __init__(self, config: DegradationConfig = None):
        self.config = config or DegradationConfig()
        self._current_level = DegradationLevel.NORMAL
        self._degradation_history: list[dict] = []

    async def execute_with_fallback(
        self,
        primary_func: Callable,
        fallback_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """执行主函数，失败时使用回退"""
        try:
            result = await primary_func(*args, **kwargs)
            self._current_level = DegradationLevel.NORMAL
            return result
        except Exception as e:
            logger.warning(f"[Degradation] Primary failed: {e}, using fallback")
            self._record_degradation("primary", str(e))

            if self.config.enable_llm_fallback:
                try:
                    result = await fallback_func(*args, **kwargs)
                    self._current_level = DegradationLevel.DEGRADED
                    return result
                except Exception as fallback_error:
                    logger.error(f"[Degradation] Fallback also failed: {fallback_error}")
                    self._record_degradation("fallback", str(fallback_error))
                    self._current_level = DegradationLevel.FAILURE

            return self._create_degraded_response(str(e))

    def _create_degraded_response(self, error: str) -> dict:
        """创建降级响应"""
        return {
            "status": "degraded",
            "error": error,
            "message": "服务暂时不可用，请稍后重试或联系管理员",
            "level": self._current_level.value,
        }

    def _record_degradation(self, stage: str, error: str):
        import time
        self._degradation_history.append({
            "timestamp": time.time(),
            "stage": stage,
            "error": error,
            "level": self._current_level.value,
        })

    def get_status(self) -> dict:
        return {
            "current_level": self._current_level.value,
            "history_count": len(self._degradation_history),
            "recent": self._degradation_history[-5:] if self._degradation_history else [],
        }

    def reset(self):
        self._current_level = DegradationLevel.NORMAL
        self._degradation_history.clear()


class ServiceHealthChecker:
    """服务健康检查"""

    def __init__(self):
        self._services = {
            "llm": {"healthy": True, "failures": 0, "last_check": 0},
            "chroma": {"healthy": True, "failures": 0, "last_check": 0},
            "checkpointer": {"healthy": True, "failures": 0, "last_check": 0},
        }
        self._failure_threshold = 3

    def record_failure(self, service: str):
        if service in self._services:
            self._services[service]["failures"] += 1
            if self._services[service]["failures"] >= self._failure_threshold:
                self._services[service]["healthy"] = False
                logger.warning(f"[Health] {service} marked as unhealthy")

    def record_success(self, service: str):
        if service in self._services:
            self._services[service]["failures"] = 0
            self._services[service]["healthy"] = True

    def is_healthy(self, service: str) -> bool:
        return self._services.get(service, {}).get("healthy", True)

    def get_all_status(self) -> dict:
        return dict(self._services)


_degradation: Optional[GracefulDegradation] = None
_health_checker: Optional[ServiceHealthChecker] = None


def get_degradation() -> GracefulDegradation:
    global _degradation
    if _degradation is None:
        _degradation = GracefulDegradation()
    return _degradation


def get_health_checker() -> ServiceHealthChecker:
    global _health_checker
    if _health_checker is None:
        _health_checker = ServiceHealthChecker()
    return _health_checker