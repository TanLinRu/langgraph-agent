"""Tests for src/rect_agent — ReAct Agent using create_react_agent"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.rect_agent.state import RectAgentState, create_initial_state
from src.rect_agent.tools import TOOLS
from src.rect_agent.tools.wrapper import build_tool_node
from src.rect_agent.hooks.prompt import build_prompt_fn
from src.rect_agent.hooks.pre_model import build_pre_model_hook
from src.rect_agent.hooks.post_model import build_post_model_hook, CRITICAL_TOOLS, _check_critical_tools
from src.rect_agent.middleware.tool_wrapper import production_tool_wrapper
from src.rect_agent.agent import RectAgent, create_rect_agent
from src.rect_agent.config import DEFAULT_CONFIG
from src.agent.rate_limiter import get_rate_limiter, get_tool_breakers


@pytest.fixture(autouse=True)
def auto_reset():
    get_tool_breakers().reset_all()


# =========== State Tests ===========

class TestRectAgentState:
    def test_create_initial_state(self):
        state = create_initial_state("test-thread")
        assert state["thread_id"] == "test-thread"
        assert state["messages"] == []
        assert state["remaining_steps"] == 50
        assert state["task_status"] == "pending"
        assert state["compression_count"] == 0
        assert state["step_count"] == 0

    def test_state_has_required_fields(self):
        state = create_initial_state()
        required = {"messages", "remaining_steps", "thread_id", "user_id", "task_status",
                    "compression_count", "token_usage", "step_count", "trace_id"}
        assert required.issubset(set(state.keys()))

    def test_state_uses_add_messages_reducer(self):
        from langgraph.graph.message import add_messages
        t = RectAgentState.__annotations__["messages"]
        assert "add_messages" in str(t)


# =========== Tool / Wrapper Tests ===========

class TestTools:
    def test_tools_loaded(self):
        assert len(TOOLS) >= 10

    def test_tool_node_built(self):
        node = build_tool_node()
        assert node is not None

    def test_critical_tools_defined(self):
        assert "execute_code" in CRITICAL_TOOLS
        assert "write_file" in CRITICAL_TOOLS
        assert "bash" in CRITICAL_TOOLS


# =========== Middleware Tests ===========

class TestToolWrapper:
    def _make_request(self, tool_name: str = "read_file", call_id: str = "call_1") -> MagicMock:
        req = MagicMock()
        req.tool_call = {"name": tool_name, "id": call_id, "args": {}}
        return req

    def test_wrapper_invokes_successfully(self):
        mock_execute = MagicMock()
        mock_execute.return_value.content = "done"

        result = production_tool_wrapper(self._make_request(), mock_execute)
        assert result.status == "success"

    def test_wrapper_skips_when_breaker_open(self):
        for _ in range(5):
            get_tool_breakers().get_breaker("read_file").record_failure()

        result = production_tool_wrapper(self._make_request(), MagicMock())
        assert result.status == "error"
        assert "熔断器" in result.content


# =========== Hooks Tests ===========

class TestPromptHook:
    def test_prompt_adds_system_message(self):
        fn = build_prompt_fn()
        messages = fn({"messages": [{"role": "user", "content": "hi"}], "user_id": "test"})
        assert len(messages) == 2
        system_msgs = [m for m in messages if getattr(m, "type", None) == "system"]
        assert len(system_msgs) >= 1


class TestPreModelHook:
    def test_rate_limiter_blocks(self):
        limiter = get_rate_limiter()
        limiter.config.max_rpm = 0
        fn = build_pre_model_hook()

        with pytest.raises(Exception) as exc:
            fn({"messages": [], "trace_id": "t1"})
        assert hasattr(exc.value, 'envelope')
        assert exc.value.envelope.error_code == "LLM_RATE_LIMIT"

    def test_circuit_breaker_blocks(self):
        llm_breaker = get_tool_breakers().get_breaker("_llm")
        for _ in range(5):
            llm_breaker.record_failure()

        limiter = get_rate_limiter()
        limiter.config.max_rpm = 9999
        fn = build_pre_model_hook()

        with pytest.raises(Exception) as exc:
            fn({"messages": [], "trace_id": "t1"})
        assert hasattr(exc.value, 'envelope')
        assert exc.value.envelope.error_code == "LLM_CIRCUIT_OPEN"


class TestPostModelHook:
    def test_detects_critical_tools(self):
        mock_msg = MagicMock()
        mock_msg.tool_calls = [{"name": "execute_code", "id": "c1", "args": {"code": "print(1)"}}]
        critical = _check_critical_tools({"messages": [mock_msg]})
        assert "execute_code" in critical

    def test_ignores_noncritical_tools(self):
        mock_msg = MagicMock()
        mock_msg.tool_calls = [{"name": "read_file", "id": "c1", "args": {"path": "/tmp"}}]
        critical = _check_critical_tools({"messages": [mock_msg]})
        assert critical == []

    def test_increments_step_count(self):
        fn = build_post_model_hook()
        result = fn({"messages": [{"role": "user", "content": "hi"}], "step_count": 0})
        assert result["step_count"] == 1


# =========== Agent Integration Tests ===========

class TestRectAgent:
    def test_agent_imports(self):
        assert RectAgent is not None
        assert create_rect_agent is not None

    def test_agent_creates_graph_with_checkpointer(self, tmp_path):
        with patch("src.rect_agent.agent.LongTermManager"), \
             patch("src.rect_agent.agent.ContextCompressor"), \
             patch("src.rect_agent.agent.get_tool_breakers"):

            from langgraph.checkpoint.sqlite import SqliteSaver
            import sqlite3

            agent = RectAgent(config=DEFAULT_CONFIG, llm=MagicMock())
            db = tmp_path / "test.db"
            conn = sqlite3.connect(str(db))
            checkpointer = SqliteSaver(conn)

            graph = agent.compile(checkpointer=checkpointer)
            assert graph is not None


# =========== Config Tests ===========

class TestConfig:
    def test_config_imports_from_agent(self):
        from src.rect_agent.config import ShortTermConfig, LongTermConfig
        assert ShortTermConfig().max_steps == 50
        assert LongTermConfig().redis_url == ""

    def test_default_config_has_budget(self):
        assert DEFAULT_CONFIG.short_term.retry_budget_limit == 0.10
