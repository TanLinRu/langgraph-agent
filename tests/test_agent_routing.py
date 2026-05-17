import pytest
from unittest.mock import patch
from src.agent.state import create_initial_state
from src.agent.config import AgentConfig, ShortTermConfig


class TestAgentRouting:
    def test_should_continue_respects_max_steps(self):
        from src.agent.agent import Agent
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.config = AgentConfig()
            agent.config.short_term.max_steps = 5
            agent.config.short_term.max_iterations = 50

            state = create_initial_state()
            state["task_status"] = "in_progress"
            state["compression_count"] = 0
            state["step_count"] = 5

            result = agent._should_continue(state)
            assert result == "end"

    def test_should_continue_continues_under_max_steps(self):
        from src.agent.agent import Agent
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.config = AgentConfig()
            agent.config.short_term.max_steps = 50
            agent.config.short_term.max_iterations = 50

            state = create_initial_state()
            state["task_status"] = "in_progress"
            state["step_count"] = 10

            result = agent._should_continue(state)
            assert result == "think"

    def test_should_continue_respects_max_compressions(self):
        from src.agent.agent import Agent
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.config = AgentConfig()
            agent.config.short_term.max_steps = 50
            agent.config.short_term.max_iterations = 50

            state = create_initial_state()
            state["task_status"] = "in_progress"
            state["compression_count"] = 5
            state["step_count"] = 3

            result = agent._should_continue(state)
            assert result == "end"

    def test_should_continue_ends_when_not_in_progress(self):
        from src.agent.agent import Agent
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.config = AgentConfig()
            agent.config.short_term.max_steps = 50
            agent.config.short_term.max_iterations = 50

            state = create_initial_state()
            state["task_status"] = "completed"
            state["step_count"] = 1

            result = agent._should_continue(state)
            assert result == "end"

    def test_config_max_steps_default(self):
        cfg = ShortTermConfig()
        assert cfg.max_steps == 50
        assert cfg.max_iterations == 50

    def test_config_max_steps_custom(self):
        cfg = ShortTermConfig(max_steps=10, max_iterations=20)
        assert cfg.max_steps == 10
        assert cfg.max_iterations == 20

    def test_should_continue_missing_step_count_defaults_to_0(self):
        from src.agent.agent import Agent
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.config = AgentConfig()
            agent.config.short_term.max_steps = 50
            agent.config.short_term.max_iterations = 50

            state = create_initial_state()
            state["task_status"] = "in_progress"
            state.pop("step_count", None)
            state["compression_count"] = 0

            result = agent._should_continue(state)
            assert result == "think"

    def test_step_count_increments(self):
        state = create_initial_state()
        state["step_count"] = state.get("step_count", 0) + 1
        assert state["step_count"] == 1