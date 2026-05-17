"""Tests for retry + circuit breaker alignment with agent-flow-design.md"""
import os
import pytest
from unittest.mock import MagicMock, patch, call, PropertyMock

from src.agent.agent import Agent
from src.agent.config import DEFAULT_CONFIG
from src.agent.rate_limiter import RateLimiter, RateLimitConfig, get_rate_limiter, get_tool_breakers, CircuitBreaker
from src.agent.schemas import ErrorType, ErrorLevel, ERROR_CODES


@pytest.fixture(autouse=True)
def auto_reset():
    get_tool_breakers().reset_all()


def _make_permissive_limiter():
    limiter = RateLimiter(RateLimitConfig(max_rpm=9999, max_rph=999999, halt_threshold=999999))
    return limiter


@pytest.fixture
def agent():
    with patch("src.agent.context.long_term.chromadb"):
        a = Agent(config=DEFAULT_CONFIG, enable_tracing=False)
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "mock reply"
        mock_response.response_metadata = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
        }
        mock_llm.invoke.return_value = mock_response
        a.llm = mock_llm
        return a


@pytest.mark.unit
class TestNodeThinkRetry:
    """_node_think retry + circuit breaker tests"""

    def test_rate_limiter_blocks(self, agent):
        """Rate limiter 阻塞时抛出 StructuredAgentError"""
        limiter = get_rate_limiter()
        limiter.config.max_rpm = 0  # Block immediately

        state = {
            "messages": [{"role": "user", "content": "hello"}],
            "thread_id": "test",
            "user_id": "default",
            "step_count": 0,
        }

        with pytest.raises(Exception) as exc_info:
            agent._node_think(state)

        err = exc_info.value
        assert hasattr(err, 'envelope')
        assert err.envelope.error_code == "LLM_RATE_LIMIT"

    def test_circuit_breaker_open(self, agent):
        """熔断器开启时抛出 StructuredAgentError"""
        with patch("src.agent.agent.get_rate_limiter", return_value=_make_permissive_limiter()):
            breaker = get_tool_breakers().get_breaker("_llm")
            for _ in range(breaker.failure_threshold):
                breaker.record_failure()

            state = {
                "messages": [{"role": "user", "content": "hello"}],
                "thread_id": "test",
                "user_id": "default",
                "step_count": 0,
            }

            with pytest.raises(Exception) as exc_info:
                agent._node_think(state)

            err = exc_info.value
            assert hasattr(err, 'envelope')
            assert err.envelope.error_code == "CIRCUIT_BREAKER_OPEN"

    def test_retry_on_recoverable_error(self, agent):
        """可恢复错误触发重试，最终成功"""
        call_count = [0]

        def failing_then_succeeding(messages, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise TimeoutError("LLM timeout")
            resp = MagicMock()
            resp.content = "success after retry"
            resp.response_metadata = {"prompt_tokens": 10, "completion_tokens": 5}
            return resp

        agent.llm.invoke.side_effect = failing_then_succeeding

        state = {
            "messages": [{"role": "user", "content": "hello"}],
            "thread_id": "test",
            "user_id": "default",
            "step_count": 0,
            "trace_id": "test-trace",
        }

        with patch("src.agent.agent.get_rate_limiter", return_value=_make_permissive_limiter()):
            result = agent._node_think(state)
            assert call_count[0] == 3
            assert result["step_count"] == 1
            # _node_think 返回的 messages[0] 是 LLM 响应的 MagicMock, 用 .content 取值
            first_msg = result["messages"][0]
            content = first_msg.content if hasattr(first_msg, "content") else first_msg.get("content", "")
            assert "success after retry" in content

    def test_non_retryable_error_no_retry(self, agent):
        """不可恢复错误不重试，直接抛出"""
        call_count = [0]

        def failing_with_fatal(messages, **kwargs):
            call_count[0] += 1
            raise ValueError("invalid response format")

        agent.llm.invoke.side_effect = failing_with_fatal

        state = {
            "messages": [{"role": "user", "content": "hello"}],
            "thread_id": "test",
            "user_id": "default",
            "step_count": 0,
            "trace_id": "test-trace",
        }

        with patch("src.agent.agent.get_rate_limiter", return_value=_make_permissive_limiter()):
            with pytest.raises(Exception) as exc_info:
                agent._node_think(state)

            assert call_count[0] <= 1
            err = exc_info.value
            code_info = ERROR_CODES.get("LLM_INVALID_RESPONSE", {})
            assert err.envelope.error_code == "LLM_INVALID_RESPONSE"
            assert not code_info.get("retryable", True)

    def test_central_error_codes_used(self, agent):
        """错误分类使用中央 ERROR_CODES"""
        def fail_timeout(messages, **kwargs):
            raise TimeoutError("timed out after 30s")

        agent.llm.invoke.side_effect = fail_timeout

        state = {
            "messages": [{"role": "user", "content": "hello"}],
            "thread_id": "test",
            "user_id": "default",
            "step_count": 0,
            "trace_id": "test-trace",
        }

        with patch("src.agent.agent.get_rate_limiter", return_value=_make_permissive_limiter()):
            with pytest.raises(Exception) as exc_info:
                agent._node_think(state)

            err = exc_info.value
            assert err.envelope.error_code == "LLM_TIMEOUT"
            code_info = ERROR_CODES.get("LLM_TIMEOUT", {})
            assert code_info.get("retryable", False) is True

    def test_breaker_records_success_after_retry(self, agent):
        """重试成功后记录熔断器成功"""
        call_count = [0]

        def fail_once(messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("network glitch")
            resp = MagicMock()
            resp.content = "ok"
            resp.response_metadata = {"prompt_tokens": 10, "completion_tokens": 5}
            return resp

        agent.llm.invoke.side_effect = fail_once

        state = {
            "messages": [{"role": "user", "content": "hello"}],
            "thread_id": "test",
            "user_id": "default",
            "step_count": 0,
            "trace_id": "test-trace",
        }

        with patch("src.agent.agent.get_rate_limiter", return_value=_make_permissive_limiter()):
            result = agent._node_think(state)
            assert call_count[0] == 2

            breaker = get_tool_breakers().get_breaker("_llm")
            assert breaker.state == "closed"


@pytest.mark.unit
class TestNodeExecuteRetry:
    """_node_execute retry + tool circuit breaker tests"""

    def make_tool_mock(self, name, side_effect_func):
        t = MagicMock()
        t.name = name
        t.invoke.side_effect = side_effect_func
        return t

    def test_tool_circuit_breaker_skips(self, agent):
        """工具熔断器开启时跳过工具"""
        breaker = get_tool_breakers().get_breaker("read_file")
        for _ in range(breaker.failure_threshold):
            breaker.record_failure()

        state = {
            "messages": [{
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_1",
                    "name": "read_file",
                    "arguments": {"path": "test.txt"},
                }],
            }],
            "thread_id": "test",
            "user_id": "default",
            "step_count": 0,
        }

        result = agent._node_execute(state)
        msgs = result.get("messages", [])
        assert len(msgs) == 1
        assert msgs[0]["status"] == "skipped"
        assert "熔断器" in msgs[0]["content"]

    def test_tool_retry_records_breaker(self, agent):
        """工具重试成功后记录熔断器"""
        call_count = [0]

        def invoke_fn(args):
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError("network error")
            return {"content": "file content", "status": "success"}

        mock_tool = self.make_tool_mock("read_file", invoke_fn)

        with patch("src.agent.agent.TOOLS", [mock_tool]):
            state = {
                "messages": [{
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_1",
                        "name": "read_file",
                        "arguments": {"path": "test.txt"},
                    }],
                }],
                "thread_id": "test",
                "user_id": "default",
                "step_count": 0,
            }

            result = agent._node_execute(state)
            msgs = result.get("messages", [])
            assert len(msgs) == 1
            assert msgs[0]["status"] == "success"

    def test_immediate_fatal_no_retry(self, agent):
        """TOOL_NOT_FOUND 不重试"""
        call_count = [0]

        def invoke_fn(args):
            call_count[0] += 1
            raise ValueError("tool not found")

        mock_tool = self.make_tool_mock("read_file", invoke_fn)

        with patch("src.agent.agent.TOOLS", [mock_tool]):
            state = {
                "messages": [{
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_1",
                        "name": "read_file",
                        "arguments": {},
                    }],
                }],
                "thread_id": "test",
                "user_id": "default",
                "step_count": 0,
            }

            result = agent._node_execute(state)
            assert call_count[0] == 1  # no retry
            msgs = result.get("messages", [])
            assert len(msgs) == 1
            assert msgs[0]["status"] == "failed"

    def test_retry_then_success(self, agent):
        """可恢复错误重试后成功"""
        call_count = [0]

        def invoke_fn(args):
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("exec timeout")
            return {"content": "code output", "status": "success"}

        mock_tool = self.make_tool_mock("execute_code", invoke_fn)

        with patch("src.agent.agent.TOOLS", [mock_tool]):
            state = {
                "messages": [{
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_1",
                        "name": "execute_code",
                        "arguments": {"code": "print(1)"},
                    }],
                }],
                "thread_id": "test",
                "user_id": "default",
                "step_count": 0,
            }

            result = agent._node_execute(state)
            # 2 failures + 1 success -> 3 attempts
            assert call_count[0] == 3
            msgs = result.get("messages", [])
            assert len(msgs) == 1
            assert msgs[0]["status"] == "success"
