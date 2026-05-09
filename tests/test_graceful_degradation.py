"""
Tests for Graceful Degradation
"""
import pytest
import asyncio
from src.agent.graceful_degradation import (
    GracefulDegradation, ServiceHealthChecker, DegradationConfig, DegradationLevel
)


class TestGracefulDegradation:
    def test_status_initializes_normal(self):
        gd = GracefulDegradation()
        assert gd._current_level == DegradationLevel.NORMAL

    def test_degraded_response_creation(self):
        gd = GracefulDegradation()
        gd._current_level = DegradationLevel.FAILURE
        result = gd._create_degraded_response("Test error")
        assert result["status"] == "degraded"
        assert result["level"] == "failure"


class TestServiceHealthChecker:
    def test_starts_healthy(self):
        shc = ServiceHealthChecker()
        assert shc.is_healthy("llm") is True

    def test_becomes_unhealthy_after_failures(self):
        shc = ServiceHealthChecker()
        shc._failure_threshold = 2

        shc.record_failure("llm")
        assert shc.is_healthy("llm") is True
        shc.record_failure("llm")
        assert shc.is_healthy("llm") is False

    def test_recovers_on_success(self):
        shc = ServiceHealthChecker()
        shc._failure_threshold = 2

        shc.record_failure("llm")
        shc.record_failure("llm")
        shc.record_success("llm")
        assert shc.is_healthy("llm") is True