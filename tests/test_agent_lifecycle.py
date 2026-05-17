import pytest
from unittest.mock import patch, MagicMock
from src.agent.agent import Agent


class TestAgentLifecycle:
    def test_pause_returns_success_on_existing_thread(self):
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.checkpointer = MagicMock()
            mock_checkpoint = {
                "channel_values": {"task_status": "in_progress", "messages": []}
            }
            agent.checkpointer.get.return_value = mock_checkpoint
            agent.checkpointer.put.return_value = None

            with patch("src.agent.agent.make_thread_id", return_value="default:default:default:test-thread"):
                result = agent.pause(thread_id="test-thread")

            assert result["status"] == "success"
            assert result["action"] == "paused"
            agent.checkpointer.put.assert_called_once()

    def test_pause_returns_error_on_nonexistent_thread(self):
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.checkpointer = MagicMock()
            agent.checkpointer.get.return_value = None

            with patch("src.agent.agent.make_thread_id", return_value="default:default:default:test-thread"):
                result = agent.pause(thread_id="test-thread")

            assert result["status"] == "error"

    def test_abort_sets_status_to_aborted(self):
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.checkpointer = MagicMock()
            mock_checkpoint = {
                "channel_values": {"task_status": "in_progress", "messages": []}
            }
            agent.checkpointer.get.return_value = mock_checkpoint
            agent.checkpointer.put.return_value = None

            with patch("src.agent.agent.make_thread_id", return_value="default:default:default:test-thread"):
                result = agent.abort(thread_id="test-thread")

            assert result["status"] == "success"
            assert result["action"] == "aborted"

    def test_resume_from_paused(self):
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.checkpointer = MagicMock()
            mock_checkpoint = {
                "channel_values": {"task_status": "paused", "messages": []}
            }
            agent.checkpointer.get.return_value = mock_checkpoint
            agent.checkpointer.put.return_value = None

            with patch("src.agent.agent.make_thread_id", return_value="default:default:default:test-thread"):
                result = agent.resume(thread_id="test-thread")

            assert result["status"] == "success"
            assert result["action"] == "resumed"

    def test_resume_from_non_paused_fails(self):
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.checkpointer = MagicMock()
            mock_checkpoint = {
                "channel_values": {"task_status": "in_progress", "messages": []}
            }
            agent.checkpointer.get.return_value = mock_checkpoint

            with patch("src.agent.agent.make_thread_id", return_value="default:default:default:test-thread"):
                result = agent.resume(thread_id="test-thread")

            assert result["status"] == "error"
            assert "不可恢复" in result["message"]

    def test_resume_from_nonexistent_thread_fails(self):
        with patch.object(Agent, "__init__", lambda self, **kw: None):
            agent = Agent.__new__(Agent)
            agent.checkpointer = MagicMock()
            agent.checkpointer.get.return_value = None

            with patch("src.agent.agent.make_thread_id", return_value="default:default:default:test-thread"):
                result = agent.resume(thread_id="test-thread")

            assert result["status"] == "error"