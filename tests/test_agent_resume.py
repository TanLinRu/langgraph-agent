import pytest
import os
import json
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestMultiTurnResume:

    def test_run_appends_to_existing_messages(self, tmp_path):
        """验证 run() 从 checkpointer 恢复已有消息并追加新输入"""
        mem_dir = str(tmp_path / "memory")
        os.environ["OPENAI_API_KEY"] = "test-key"

        with patch("src.agent.context.long_term.chromadb"):
            from src.agent.agent import create_agent

            agent = create_agent(
                model="openai:gpt-4o-mini",
                api_key="test-key",
                base_url="https://api.openai.com/v1",
            )

            agent.config.long_term.memory_dir = tmp_path / "memory"
            agent.config.long_term.chroma_persist_dir = str(tmp_path / "memory/chroma")
            agent.config.long_term.vector_enabled = False

            mock_llm = MagicMock()
            mock_llm.invoke.return_value = {
                "role": "assistant",
                "content": "reply",
                "tool_calls": [],
            }
            agent.llm = mock_llm

            thread_id = "test-resume"

            result1 = agent.run("第一轮问题", thread_id=thread_id)
            assert result1["status"] == "success"

            checkpoint = agent.checkpointer.get({"configurable": {"thread_id": thread_id}})
            assert checkpoint is not None

            channel_values = checkpoint.get("channel_values", {})
            messages = channel_values.get("messages", [])
            assert len(messages) > 0

    def test_multi_turn_messages_accumulate(self, tmp_path):
        """验证多次 run 调用后消息正确累积"""
        mem_dir = str(tmp_path / "memory")
        os.environ["OPENAI_API_KEY"] = "test-key"

        with patch("src.agent.context.long_term.chromadb"):
            from src.agent.agent import create_agent

            agent = create_agent(
                model="openai:gpt-4o-mini",
                api_key="test-key",
                base_url="https://api.openai.com/v1",
            )

            agent.config.long_term.memory_dir = tmp_path / "memory"
            agent.config.long_term.chroma_persist_dir = str(tmp_path / "memory/chroma")
            agent.config.long_term.vector_enabled = False

            mock_llm = MagicMock()
            mock_llm.invoke.return_value = {
                "role": "assistant",
                "content": "reply",
                "tool_calls": [],
            }
            agent.llm = mock_llm

            thread_id = "test-accumulate"

            result1 = agent.run("问题1", thread_id=thread_id)
            assert result1["status"] == "success"

            result2 = agent.run("问题2", thread_id=thread_id)
            assert result2["status"] == "success"

            assert mock_llm.invoke.call_count == 2

            second_call_args = mock_llm.invoke.call_args_list[1][0][0]
            user_msgs = [m for m in second_call_args if isinstance(m, dict) and m.get("role") == "user"]
            assert len(user_msgs) >= 2
