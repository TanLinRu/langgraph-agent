import pytest
from unittest.mock import MagicMock, patch


class TestShouldExecute:

    def _create_agent(self):
        from src.agent.agent import Agent, create_agent
        return create_agent(
            model="openai:gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
        )

    def test_routes_to_execute_when_tool_calls(self):
        agent = self._create_agent()
        state = {
            "messages": [{"role": "assistant", "tool_calls": [{"name": "read_file"}]}]
        }
        assert agent._should_execute(state) == "execute"

    def test_routes_to_end_when_direct_reply(self):
        agent = self._create_agent()
        state = {
            "messages": [{"role": "assistant", "content": "Hello"}]
        }
        assert agent._should_execute(state) == "end"

    def test_routes_to_execute_when_empty_messages(self):
        agent = self._create_agent()
        state = {"messages": []}
        assert agent._should_execute(state) == "execute"


class TestShouldContinue:

    def _create_agent(self):
        from src.agent.agent import Agent, create_agent
        return create_agent(
            model="openai:gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
        )

    def test_routes_to_think_when_in_progress_and_low_compression(self):
        agent = self._create_agent()
        state = {
            "task_status": "in_progress",
            "compression_count": 2,
        }
        assert agent._should_continue(state) == "think"

    def test_routes_to_end_when_completed(self):
        agent = self._create_agent()
        state = {
            "task_status": "completed",
            "compression_count": 1,
        }
        assert agent._should_continue(state) == "end"

    def test_routes_to_end_when_max_compression(self):
        agent = self._create_agent()
        state = {
            "task_status": "in_progress",
            "compression_count": 5,
        }
        assert agent._should_continue(state) == "end"

    def test_routes_to_think_when_below_max_compression(self):
        agent = self._create_agent()
        state = {
            "task_status": "in_progress",
            "compression_count": 4,
        }
        assert agent._should_continue(state) == "think"

    def test_routes_to_end_when_compression_exceeds_max(self):
        agent = self._create_agent()
        state = {
            "task_status": "in_progress",
            "compression_count": 10,
        }
        assert agent._should_continue(state) == "end"
