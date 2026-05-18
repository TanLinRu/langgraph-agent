"""
Rate Limiter and Circuit Breaker

提供:
- 请求频率限制 (RPM)
- 成本熔断器 (防止异常费用)
- 工具级别熔断器 (可选 Redis 持久化)
"""
import time
import logging
from collections import deque
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import redis as redis_module
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis_module = None


@dataclass
class RateLimitConfig:
    max_rpm: int = 60
    max_rph: int = 1000
    max_cost_per_hour: float = 10.0
    alert_threshold: float = 5.0
    halt_threshold: float = 20.0


class RateLimiter:
    """请求频率限制器"""

    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self._rpm_history: deque = deque()
        self._rph_history: deque = deque()
        self._hourly_cost: float = 0.0
        self._cost_history: list[tuple[float, float]] = []
        self._blocked = False

    def check_limit(self) -> bool:
        """检查是否超出限制"""
        now = time.time()

        self._rpm_history.append(now)
        self._rpm_history = deque(
            t for t in self._rpm_history if now - t < 60
        )

        rpm = len(self._rpm_history)
        if rpm > self.config.max_rpm:
            logger.warning(f"[RateLimiter] RPM limit exceeded: {rpm}/{self.config.max_rpm}")
            return False

        return True

    def record_request(self):
        """记录请求"""
        now = time.time()
        self._rpm_history.append(now)

    def add_cost(self, cost: float):
        """记录成本"""
        now = time.time()
        self._hourly_cost += cost
        self._cost_history.append((now, cost))

        self._cost_history = [
            (t, c) for t, c in self._cost_history if now - t < 3600
        ]

    def check_cost_limit(self) -> tuple[bool, str]:
        """检查成本限制"""
        if self._hourly_cost >= self.config.halt_threshold:
            self._blocked = True
            return False, f"Cost halt: ${self._hourly_cost:.2f} exceeds ${self.config.halt_threshold}"
        elif self._hourly_cost >= self.config.alert_threshold:
            return False, f"Cost alert: ${self._hourly_cost:.2f}"
        return True, ""

    def reset_cost(self):
        """重置成本计数"""
        self._hourly_cost = 0.0
        self._cost_history.clear()
        self._blocked = False


class CircuitBreaker:
    """熔断器 - 防止级联失败"""

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half-open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self.failures = 0
        self.successes = 0
        self.last_failure_time: Optional[float] = None
        self.state = self.STATE_CLOSED

    def record_success(self):
        """记录成功"""
        if self.state == self.STATE_HALF_OPEN:
            self.successes += 1
            if self.successes >= self.success_threshold:
                self._reset()
                logger.info("[CircuitBreaker] Recovered to closed state")
        else:
            self.failures = 0

    def record_failure(self):
        """记录失败"""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.state == self.STATE_HALF_OPEN:
            self._open()
            logger.warning("[CircuitBreaker] Half-open failed, opening circuit")
        elif self.failures >= self.failure_threshold:
            self._open()
            logger.warning(f"[CircuitBreaker] Opened circuit after {self.failures} failures")

    def can_execute(self) -> bool:
        """检查是否可以执行"""
        if self.state == self.STATE_CLOSED:
            return True

        if self.state == self.STATE_OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = self.STATE_HALF_OPEN
                self.successes = 0
                logger.info("[CircuitBreaker] Half-open: testing recovery")
                return True
            return False

        return True

    def _open(self):
        self.state = self.STATE_OPEN

    def _reset(self):
        self.state = self.STATE_CLOSED
        self.failures = 0
        self.successes = 0
        self.last_failure_time = None


class RedisCircuitBreaker(CircuitBreaker):
    """熔断器 - 带可选 Redis 持久化"""

    def __init__(self, redis_client=None, key="", **kwargs):
        super().__init__(**kwargs)
        self._redis = redis_client
        self._redis_key = key
        if self._redis and self._redis_key:
            self._load_from_redis()

    def _load_from_redis(self):
        try:
            data = self._redis.hgetall(self._redis_key)
            if data:
                self.failures = int(data.get(b"failures", 0))
                self.successes = int(data.get(b"successes", 0))
                last_fail = data.get(b"last_failure_time")
                self.last_failure_time = float(last_fail) if last_fail else None
                self.state = data.get(b"state", b"closed").decode()
        except Exception:
            logger.warning("[RedisCircuitBreaker] Failed to load state from Redis", exc_info=True)

    def _save_to_redis(self):
        if not self._redis or not self._redis_key:
            return
        try:
            self._redis.hset(self._redis_key, mapping={
                "failures": self.failures,
                "successes": self.successes,
                "last_failure_time": self.last_failure_time or "",
                "state": self.state,
            })
        except Exception:
            logger.warning("[RedisCircuitBreaker] Failed to save state to Redis", exc_info=True)

    def record_success(self):
        super().record_success()
        self._save_to_redis()

    def record_failure(self):
        super().record_failure()
        self._save_to_redis()

    def _open(self):
        super()._open()
        self._save_to_redis()

    def _reset(self):
        super()._reset()
        self._save_to_redis()


class ToolCircuitBreaker:
    """工具级别熔断器管理"""

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_breaker(self, tool_name: str) -> CircuitBreaker:
        if tool_name not in self._breakers:
            if self._redis:
                self._breakers[tool_name] = RedisCircuitBreaker(
                    redis_client=self._redis, key=f"cb:{tool_name}"
                )
            else:
                self._breakers[tool_name] = CircuitBreaker()
        return self._breakers[tool_name]

    def record_success(self, tool_name: str):
        self.get_breaker(tool_name).record_success()

    def record_failure(self, tool_name: str):
        self.get_breaker(tool_name).record_failure()

    def can_execute(self, tool_name: str) -> bool:
        return self.get_breaker(tool_name).can_execute()

    def reset_all(self):
        for breaker in self._breakers.values():
            breaker._reset()


def _create_redis_client(redis_url: str):
    if not REDIS_AVAILABLE:
        logger.warning("[RateLimiter] redis package not installed, install with: pip install langgraph-agent[reliability]")
        return None
    try:
        client = redis_module.from_url(redis_url, decode_responses=False)
        client.ping()
        logger.info(f"[RateLimiter] Connected to Redis at {redis_url}")
        return client
    except Exception:
        logger.warning(f"[RateLimiter] Failed to connect to Redis at {redis_url}", exc_info=True)
        return None


_rate_limiter: Optional[RateLimiter] = None
_tool_breakers: Optional[ToolCircuitBreaker] = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def get_tool_breakers(redis_url: str = "") -> ToolCircuitBreaker:
    global _tool_breakers
    if _tool_breakers is None:
        redis_client = _create_redis_client(redis_url) if redis_url else None
        _tool_breakers = ToolCircuitBreaker(redis_client=redis_client)
    return _tool_breakers