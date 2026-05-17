import pytest
import asyncio
from src.agent.schemas import (
    ErrorType,
    ErrorLevel,
    StructuredAgentError,
    structured_catch,
)


class TestStructuredCatch:
    def test_sync_function_success(self):
        @structured_catch(error_code="CUSTOM_ERROR")
        def succeed():
            return "ok"

        result = succeed()
        assert result == "ok"

    def test_sync_function_raises_structured(self):
        @structured_catch(
            error_code="TOOL_EXEC_ERROR",
            error_type=ErrorType.RECOVERABLE,
            error_level=ErrorLevel.MEDIUM,
        )
        def fail():
            raise ValueError("test error")

        with pytest.raises(StructuredAgentError) as record:
            fail()
        assert record.value.envelope.error_code == "TOOL_EXEC_ERROR"
        assert record.value.envelope.error_type == ErrorType.RECOVERABLE

    def test_sync_function_suppress_returns_none(self):
        @structured_catch(
            error_code="LLM_ENRICH_FAILED",
            error_type=ErrorType.RECOVERABLE,
            suppress=True,
            log_level="warning",
        )
        def fail_suppressed():
            raise RuntimeError("ignored")

        result = fail_suppressed()
        assert result is None

    def test_sync_function_non_structured_propagates(self):
        @structured_catch(error_code="CUSTOM")
        def fail_non_structured():
            raise StructuredAgentError(
                error_code="PREEXISTING",
                error_type=ErrorType.FATAL,
                message="already structured",
            )

        with pytest.raises(StructuredAgentError) as record:
            fail_non_structured()
        assert record.value.envelope.error_code == "PREEXISTING"

    def test_async_function_success(self):
        @structured_catch(error_code="ASYNC_ERROR")
        async def async_succeed():
            return "async ok"

        result = asyncio.run(async_succeed())
        assert result == "async ok"

    def test_async_function_raises(self):
        @structured_catch(
            error_code="TOOL_EXEC_TIMEOUT",
            error_type=ErrorType.RECOVERABLE,
        )
        async def async_fail():
            raise TimeoutError("timeout")

        with pytest.raises(StructuredAgentError) as record:
            asyncio.run(async_fail())
        assert record.value.envelope.error_code == "TOOL_EXEC_TIMEOUT"

    def test_retryable_flag_false(self):
        @structured_catch(
            error_code="TOOL_NOT_FOUND",
            error_type=ErrorType.FATAL,
            retryable=False,
            error_level=ErrorLevel.HIGH,
        )
        def fail_fatal():
            raise FileNotFoundError("not found")

        with pytest.raises(StructuredAgentError) as record:
            fail_fatal()
        env = record.value.envelope
        assert env.retryable is False
        assert env.error_level == ErrorLevel.HIGH


class TestStructuredCatchIntegration:
    def test_catch_wraps_to_envelope(self):
        @structured_catch(
            error_code="INTEGRATION_TEST",
            error_type=ErrorType.SYSTEM,
            error_level=ErrorLevel.HIGH,
        )
        def raise_custom():
            raise IOError("io error")

        with pytest.raises(StructuredAgentError) as record:
            raise_custom()
        env = record.value.envelope
        assert env.error_code == "INTEGRATION_TEST"
        assert env.error_type == ErrorType.SYSTEM
        assert "io error" in env.message

    def test_context_snapshot_includes_args(self):
        @structured_catch(
            error_code="ARG_ERROR",
            error_type=ErrorType.FATAL,
        )
        def raise_with_args(x, y=None):
            raise ValueError("bad args")

        with pytest.raises(StructuredAgentError) as record:
            raise_with_args("test_input", y={"key": "value"})
        ctx = record.value.envelope.context_snapshot
        assert ctx["func"] == "raise_with_args"
        assert "kwargs" in ctx["args"] or "args_count" in ctx["args"]

    def test_trace_id_propagation(self):
        @structured_catch(error_code="TRACE_TEST")
        def raise_with_trace():
            raise RuntimeError("trace test")

        with pytest.raises(StructuredAgentError) as record:
            raise_with_trace()
        assert record.value.envelope.trace_id != ""