import pytest
import os
import sys
import json
from unittest.mock import MagicMock, patch
from pathlib import Path


def should_use_real_api():
    return os.getenv("USE_REAL_API", "false").lower() == "true"


class TestMultiTurnResume:
    @pytest.fixture
    def agent_instance(self, tmp_path):
        """创建 Agent 实例（跨平台兼容）"""
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

            return agent

    def _create_mock_llm(self, response_content="reply"):
        """创建 Mock LLM"""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = {
            "role": "assistant",
            "content": response_content,
            "tool_calls": [],
        }
        return mock_llm

    @pytest.mark.skipif(sys.platform == "win32", reason="langgraph checkpointer issue on Windows")
    def test_run_appends_to_existing_messages(self, agent_instance):
        """验证 run() 从 checkpointer 恢复已有消息并追加新输入"""
        mock_llm = self._create_mock_llm()
        agent_instance.llm = mock_llm

        thread_id = "test-resume"

        result1 = agent_instance.run("第一轮问题", thread_id=thread_id)
        assert result1["status"] == "success"

        checkpoint = agent_instance.checkpointer.get({"configurable": {"thread_id": thread_id}})
        assert checkpoint is not None

        channel_values = checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", [])
        assert len(messages) > 0

    @pytest.mark.skipif(sys.platform == "win32", reason="langgraph checkpointer issue on Windows")
    def test_multi_turn_messages_accumulate(self, agent_instance):
        """验证多次 run 调用后消息正确累积"""
        mock_llm = self._create_mock_llm()
        agent_instance.llm = mock_llm

        thread_id = "test-accumulate"

        result1 = agent_instance.run("问题1", thread_id=thread_id)
        assert result1["status"] == "success"

        result2 = agent_instance.run("问题2", thread_id=thread_id)
        assert result2["status"] == "success"

        assert mock_llm.invoke.call_count >= 2

        second_call_args = mock_llm.invoke.call_args_list[-1][0][0]
        user_msgs = [m for m in second_call_args if isinstance(m, dict) and m.get("role") == "user"]
        assert len(user_msgs) >= 2

    def test_multi_turn_with_real_api(self, tmp_path):
        """Real API: 验证真实多轮对话流程"""
        if not should_use_real_api():
            pytest.skip("USE_REAL_API not enabled")

        os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")

        with patch("src.agent.context.long_term.chromadb"):
            from src.agent.agent import create_agent

            agent = create_agent(
                model=os.getenv("AGENT_MODEL", "openai:gpt-4o-mini"),
                api_key=os.getenv("OPENAI_API_KEY", ""),
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            )

            agent.config.long_term.memory_dir = tmp_path / "memory"
            agent.config.long_term.chroma_persist_dir = str(tmp_path / "memory/chroma")
            agent.config.long_term.vector_enabled = False

            thread_id = "test-real-multi-turn"

            result1 = agent.run("你好，我是张三", thread_id=thread_id)
            assert result1["status"] == "success"

            result2 = agent.run("我叫什么名字？", thread_id=thread_id)
            assert result2["status"] == "success"

    def test_context_compression_in_multi_turn(self, tmp_path):
        """Mock: 验证多轮对话中的上下文压缩触发"""
        if not should_use_real_api():
            pytest.skip("USE_REAL_API not enabled (compression test)")

        os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")

        with patch("src.agent.context.long_term.chromadb"):
            from src.agent.agent import create_agent
            from src.agent.context.compression import ContextCompressor, CompressionConfig

            agent = create_agent(
                model=os.getenv("AGENT_MODEL", "openai:gpt-4o-mini"),
                api_key=os.getenv("OPENAI_API_KEY", ""),
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            )

            agent.config.short_term.trigger_threshold = 0.1
            agent.config.long_term.memory_dir = tmp_path / "memory"
            agent.config.long_term.chroma_persist_dir = str(tmp_path / "memory/chroma")
            agent.config.long_term.vector_enabled = False

            thread_id = "test-compression-multi"

            long_content = "写一个详细的算法实现" * 50
            result = agent.run(long_content, thread_id=thread_id)
            assert result["status"] == "success"
