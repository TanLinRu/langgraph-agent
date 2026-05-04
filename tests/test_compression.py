import pytest
from unittest.mock import MagicMock


class TestContextCompression:

    def _create_compressor(self, keep_recent=5, mock_llm=None):
        from src.agent.context.compression import ContextCompressor, CompressionConfig

        config = CompressionConfig(
            max_tokens=128000,
            trigger_threshold=0.0,  # 强制触发压缩
            keep_recent=keep_recent,
            summary_max_tokens=500,
        )
        return ContextCompressor(config, llm=mock_llm)

    def test_compress_preserves_recent_user_assistant_messages(self):
        """验证压缩后保留最近 N 条 user/assistant 消息"""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="对话摘要")

        compressor = self._create_compressor(keep_recent=3, mock_llm=mock_llm)

        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
            {"role": "assistant", "content": "a3"},
            {"role": "user", "content": "u4"},
            {"role": "assistant", "content": "a4"},
        ]

        compressed = compressor.compress(messages)

        roles = [m.get("role") for m in compressed]
        assert "system" in roles

        user_assistant_count = sum(
            1 for m in compressed if m.get("role") in ("user", "assistant")
        )
        assert user_assistant_count == 3

        last_user_msg = [m for m in compressed if m.get("role") == "user"][-1]
        assert last_user_msg["content"] == "u4"

    def test_compress_preserves_recent_tool_results(self):
        """验证压缩后保留最近 N 条 tool 结果"""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="对话摘要")

        compressor = self._create_compressor(keep_recent=3, mock_llm=mock_llm)

        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "tool", "content": "result1"},
            {"role": "tool", "content": "result2"},
            {"role": "tool", "content": "result3"},
            {"role": "tool", "content": "result4"},
            {"role": "tool", "content": "result5"},
        ]

        compressed = compressor.compress(messages)

        tool_count = sum(1 for m in compressed if m.get("role") == "tool")
        assert tool_count >= 3

    def test_compress_does_not_compress_when_below_threshold(self):
        """验证低于阈值时不压缩"""
        mock_llm = MagicMock()

        compressor = self._create_compressor(keep_recent=5, mock_llm=mock_llm)

        messages = [
            {"role": "user", "content": "short"},
            {"role": "assistant", "content": "short"},
        ]

        compressor.config.trigger_threshold = 0.99

        compressed = compressor.compress(messages)
        assert compressed == messages
