import pytest
import time
from unittest.mock import patch, MagicMock
from src.agent.schemas import (
    ErrorEnvelope,
    ErrorType,
    ErrorLevel,
    AgentInput,
    AgentOutput,
    StructuredAgentError,
    ERROR_CODES,
    structured_catch,
    _get_or_create_trace_id,
)


class TestErrorEnvelope:
    def test_creation(self):
        env = ErrorEnvelope(
            error_code="TOOL_EXEC_ERROR",
            error_type=ErrorType.RECOVERABLE,
            message="Tool failed",
            retryable=True,
            retry_after_ms=1000,
        )
        assert env.error_code == "TOOL_EXEC_ERROR"
        assert env.error_type == ErrorType.RECOVERABLE
        assert env.retryable is True
        assert env.timestamp != ""

    def test_from_exception(self):
        exc = ValueError("invalid input")
        env = ErrorEnvelope.from_exception(exc, error_code="TOOL_ARGUMENT_ERROR")
        assert env.error_code == "TOOL_ARGUMENT_ERROR"
        assert env.message == "invalid input"
        assert env.error_type == ErrorType.FATAL

    def test_to_dict(self):
        env = ErrorEnvelope(
            error_code="LLM_TIMEOUT",
            error_type=ErrorType.RECOVERABLE,
            message="timeout",
            retryable=True,
            retry_after_ms=2000,
            trace_id="trace-123",
            context_snapshot={"key": "value"},
            fallback_action="retry_later",
            error_level=ErrorLevel.MEDIUM,
            timestamp="2026-01-01T00:00:00Z",
            tool_name="llm",
            step=5,
        )
        d = env.to_dict()
        assert len(d) == 12
        assert d["error_code"] == "LLM_TIMEOUT"
        assert d["trace_id"] == "trace-123"
        assert d["step"] == 5

    def test_to_jsonrpc(self):
        env = ErrorEnvelope(
            error_code="LLM_TIMEOUT",
            error_type=ErrorType.RECOVERABLE,
            message="timeout",
            retryable=True,
        )
        rpc = env.to_jsonrpc()
        assert rpc["code"] == -32000
        assert "[LLM_TIMEOUT]" in rpc["message"]
        assert "data" in rpc

    def test_error_codes_lookup(self):
        info = ERROR_CODES.get("LLM_TIMEOUT")
        assert info is not None
        assert info["error_code"] == "LLM_TIMEOUT"
        assert info["retryable"] is True

    def test_error_level_critical_check(self):
        high = ErrorEnvelope(
            error_code="TOOL_NOT_FOUND",
            error_type=ErrorType.FATAL,
            message="not found",
            error_level=ErrorLevel.HIGH,
        )
        assert high.is_critical() is True
        assert high.should_retry() is False

        medium = ErrorEnvelope(
            error_code="LLM_TIMEOUT",
            error_type=ErrorType.RECOVERABLE,
            message="timeout",
            error_level=ErrorLevel.MEDIUM,
        )
        assert medium.is_critical() is False
        assert medium.should_retry() is True

    def test_structured_agent_error_raise(self):
        err = StructuredAgentError(
            error_code="TOOL_EXEC_ERROR",
            error_type=ErrorType.RECOVERABLE,
            message="exec failed",
        )
        with pytest.raises(StructuredAgentError) as record:
            raise err
        assert record.value.envelope.error_code == "TOOL_EXEC_ERROR"

    def test_serialization_roundtrip(self):
        original = ErrorEnvelope(
            error_code="BUDGET_EXHAUSTED",
            error_type=ErrorType.FATAL,
            message="budget",
            retryable=False,
            retry_after_ms=0,
            trace_id="round-trip-test",
            context_snapshot={"original": True},
            fallback_action="abort",
            error_level=ErrorLevel.CRITICAL,
            timestamp="2026-01-01T00:00:00Z",
            tool_name="test_tool",
            step=99,
        )
        d = original.to_dict()
        restored = ErrorEnvelope(
            error_code=d["error_code"],
            error_type=ErrorType(d["error_type"]),
            message=d["message"],
            retryable=d["retryable"],
            retry_after_ms=d["retry_after_ms"],
            trace_id=d["trace_id"],
            context_snapshot=d["context_snapshot"],
            fallback_action=d["fallback_action"],
            error_level=ErrorLevel(d["error_level"]),
            timestamp=d["timestamp"],
            tool_name=d["tool_name"],
            step=d["step"],
        )
        assert restored.error_code == original.error_code
        assert restored.trace_id == original.trace_id
        assert restored.step == original.step

    def test_from_exception_with_error_codes_map(self):
        exc = ValueError("test error")
        env = ErrorEnvelope.from_exception(exc)
        assert env.error_code == "INTERNAL_ERROR"
        assert env.error_level == ErrorLevel.HIGH

    def test_should_retry_non_retryable(self):
        env = ErrorEnvelope(
            error_code="TOOL_NOT_FOUND",
            error_type=ErrorType.FATAL,
            message="not found",
            retryable=False,
            error_level=ErrorLevel.HIGH,
        )
        assert env.should_retry() is False


class TestStructuredAgentError:
    def test_raise_and_catch(self):
        err = StructuredAgentError(
            error_code="SUPERVISOR_BUILD_ERROR",
            error_type=ErrorType.FATAL,
            message="build failed",
            error_level=ErrorLevel.HIGH,
        )
        caught = None
        try:
            raise err
        except StructuredAgentError as e:
            caught = e
        assert caught is not None
        assert caught.envelope.error_code == "SUPERVISOR_BUILD_ERROR"

    def test_from_exception(self):
        exc = RuntimeError("runtime error")
        err = StructuredAgentError.from_exception(exc, trace_id="trace-abc")
        assert err.envelope.trace_id == "trace-abc"
        assert str(err) == "runtime error"

    def test_to_envelope(self):
        err = StructuredAgentError(
            error_code="LLM_API_ERROR",
            error_type=ErrorType.RECOVERABLE,
            message="api error",
            error_level=ErrorLevel.MEDIUM,
        )
        env = err.to_envelope()
        assert env.error_code == "LLM_API_ERROR"
        assert env.error_level == ErrorLevel.MEDIUM


class TestGetOrCreateTraceId:
    def test_returns_existing_trace(self):
        with patch("src.agent.trace_context.get_trace_id", return_value="existing-tid"):
            tid = _get_or_create_trace_id()
            assert tid == "existing-tid"

    def test_generates_new_trace(self):
        with patch("src.agent.trace_context.get_trace_id", return_value=""):
            with patch("src.agent.trace_context.generate_trace_id", return_value="generated-tid"):
                tid = _get_or_create_trace_id()
                assert tid == "generated-tid"

    def test_fallback_on_import_error(self):
        with patch("src.agent.trace_context.get_trace_id", side_effect=ImportError):
            tid = _get_or_create_trace_id()
            assert tid != ""


class TestErrorCodes:
    def test_all_codes_have_required_fields(self):
        for code, info in ERROR_CODES.items():
            assert "error_code" in info
            assert "error_type" in info
            assert "retryable" in info
            assert "level" in info
            assert isinstance(info["retryable"], bool)

    def test_error_type_enum_count(self):
        assert len(ErrorType) == 4

    def test_error_level_enum_count(self):
        assert len(ErrorLevel) == 4

    def test_critical_levels(self):
        assert ErrorLevel.LOW == ErrorLevel(0)
        assert ErrorLevel.CRITICAL == ErrorLevel(3)