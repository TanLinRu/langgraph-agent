"""
Tests for Rate Limiter and Circuit Breaker
"""
import pytest
import time
from src.agent.rate_limiter import (
    RateLimiter, CircuitBreaker, ToolCircuitBreaker, RateLimitConfig
)


class TestRateLimiter:
    def test_allows_requests_under_limit(self):
        limiter = RateLimitConfig(max_rpm=10)
        rl = RateLimiter(limiter)

        for _ in range(5):
            assert rl.check_limit() is True

    def test_blocks_over_limit(self):
        limiter = RateLimitConfig(max_rpm=2)
        rl = RateLimiter(limiter)

        rl.check_limit()
        rl.check_limit()
        assert rl.check_limit() is False

    def test_cost_alert_threshold(self):
        limiter = RateLimitConfig(alert_threshold=1.0, halt_threshold=10.0)
        rl = RateLimiter(limiter)

        rl.add_cost(0.5)
        can_pass, msg = rl.check_cost_limit()
        assert can_pass is True

        rl.add_cost(5.0)
        can_pass, msg = rl.check_cost_limit()
        assert can_pass is False
        assert "alert" in msg.lower()

    def test_cost_halt_threshold(self):
        limiter = RateLimitConfig(halt_threshold=1.0)
        rl = RateLimiter(limiter)

        rl.add_cost(2.0)
        can_pass, msg = rl.check_cost_limit()
        assert can_pass is False
        assert "halt" in msg.lower()


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.STATE_CLOSED
        assert cb.can_execute() is True

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        assert cb.can_execute() is True
        cb.record_failure()
        assert cb.can_execute() is False
        assert cb.state == CircuitBreaker.STATE_OPEN

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)

        cb.record_failure()
        assert cb.state == CircuitBreaker.STATE_OPEN

        time.sleep(0.01)
        assert cb.can_execute() is True
        assert cb.state == CircuitBreaker.STATE_HALF_OPEN

    def test_closes_after_success(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0, success_threshold=2)

        cb.record_failure()
        time.sleep(0.01)
        cb.can_execute()

        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitBreaker.STATE_CLOSED


class TestToolCircuitBreaker:
    def test_separate_breakers_per_tool(self):
        tcb = ToolCircuitBreaker()
        cb_a = tcb.get_breaker("tool_a")
        cb_a.failure_threshold = 3

        tcb.record_failure("tool_a")
        tcb.record_failure("tool_a")
        tcb.record_failure("tool_a")

        assert tcb.can_execute("tool_a") is False
        assert tcb.can_execute("tool_b") is True

    def test_get_breaker_creates_new(self):
        tcb = ToolCircuitBreaker()
        breaker = tcb.get_breaker("new_tool")
        assert breaker is not None
        assert tcb.can_execute("new_tool") is True