from dataclasses import dataclass, field
from src.agent.rate_limiter import RateLimiter, ToolCircuitBreaker, get_rate_limiter, get_tool_breakers
from src.agent.config import AgentConfig
from src.agent.graceful_degradation import ServiceHealthChecker


@dataclass
class RectContext:
    """有限范围的依赖上下文，不替代 LangGraph State。

    所有字段都有默认工厂，无参构造时全部使用全局函数。
    """
    rate_limiter: RateLimiter = field(default_factory=get_rate_limiter)
    tool_breakers: ToolCircuitBreaker = field(default_factory=get_tool_breakers)
    config: AgentConfig | None = None
    health_checker: ServiceHealthChecker | None = None
