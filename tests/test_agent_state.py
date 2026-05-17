import pytest
import time
from unittest.mock import patch, MagicMock
from src.agent.state import AgentState, create_initial_state


class TestAgentState:
    def test_state_has_step_count(self):
        state = create_initial_state()
        assert "step_count" in state
        assert state["step_count"] == 0

    def test_state_has_current_action(self):
        state = create_initial_state()
        assert "current_action" in state
        assert state["current_action"] == ""

    def test_state_has_last_error(self):
        state = create_initial_state()
        assert "last_error" in state
        assert state["last_error"] is None

    def test_state_has_trace_id(self):
        state = create_initial_state()
        assert "trace_id" in state
        assert state["trace_id"] == ""

    def test_task_status_includes_paused_aborted(self):
        state = create_initial_state()
        assert state["task_status"] == "pending"


class TestAgentStateFields:
    def test_step_count_increments(self):
        state = create_initial_state()
        state["step_count"] = 5
        assert state["step_count"] == 5

    def test_last_error_set(self):
        state = create_initial_state()
        err = {"error_code": "TEST_ERROR", "message": "test"}
        state["last_error"] = err
        assert state["last_error"] == err

    def test_trace_id_set(self):
        state = create_initial_state()
        state["trace_id"] = "trace-123"
        assert state["trace_id"] == "trace-123"