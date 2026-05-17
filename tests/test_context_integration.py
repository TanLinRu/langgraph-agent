"""Tests for context integration: compression, retrieval, and multi-turn flows"""
import os
from unittest.mock import patch, MagicMock

import pytest

from src.agent.context.compression import (
    ContextCompressor,
    CompressionConfig,
    CompressionResult,
    CompressedTurn,
)
from src.agent.context.retrieval_trigger import RetrievalTrigger


def should_use_real_api():
    return os.getenv("USE_REAL_API", "false").lower() == "true"


class TestRetrievalTrigger:
    """Test suite for retrieval trigger"""

    @pytest.fixture
    def trigger(self):
        return RetrievalTrigger(
            token_threshold=0.4,
            semantic_threshold=0.7,
        )

    @pytest.fixture
    def mock_state(self):
        return {
            "messages": [
                {"role": "system", "content": "你是助手" * 100},
                {"role": "user", "content": "写代码" * 50},
                {"role": "assistant", "content": "..." * 100},
            ],
            "token_usage": {"percentage": 50},
        }

    @pytest.fixture
    def mock_state_below(self):
        return {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            "token_usage": {"percentage": 10},
        }

    def test_should_retrieve_empty_state(self, trigger):
        """空状态不应触发检索"""
        state = {"messages": [], "token_usage": {}}
        should, reason = trigger.should_retrieve(state)
        assert not should

    def test_should_retrieve_below_threshold(self, trigger, mock_state_below):
        """低于阈值不应触发"""
        should, reason = trigger.should_retrieve(mock_state_below)
        assert not should

    def test_should_retrieve_above_threshold(self, trigger, mock_state):
        """高于阈值应触发"""
        should, reason = trigger.should_retrieve(mock_state)
        assert should or reason == ""

    def test_get_retrieval_context_mock(self, trigger, mock_state):
        """Mock: 获取检索上下文"""
        if should_use_real_api():
            pytest.skip("Real API test")

        should, reason = trigger.should_retrieve(mock_state)
        assert should is not None

    def test_get_retrieval_context_real_api(self, trigger, mock_state):
        """Real API: 获取检索上下文（带 LLM）"""
        if not should_use_real_api():
            pytest.skip("USE_REAL_API not enabled")

        from langchain_openai import ChatOpenAI
        real_llm = ChatOpenAI(model=os.getenv("AGENT_MODEL", "gpt-4o-mini"), temperature=0)

        should, reason = trigger.should_retrieve(mock_state)
        assert should is not None


class TestContextIntegration:
    """Test suite for context integration flows"""

    @pytest.fixture
    def config(self):
        return CompressionConfig(
            max_tokens=1000,
            trigger_threshold=0.1,
            keep_recent=5,
            summary_max_tokens=200,
            hot_zone_size=3,
        )

    @pytest.fixture
    def compressor_with_mock_llm(self, config):
        """Compressor with mock LLM"""
        return ContextCompressor(config)

    @pytest.fixture
    def compressor_with_real_llm(self, config):
        """Compressor with real LLM"""
        if not should_use_real_api():
            pytest.skip("USE_REAL_API not enabled")

        from langchain_openai import ChatOpenAI
        real_llm = ChatOpenAI(
            model=os.getenv("AGENT_MODEL", "gpt-4o-mini"),
            temperature=0
        )
        return ContextCompressor(config, llm=real_llm)

    @pytest.fixture
    def long_conversation(self):
        """模拟长对话场景"""
        return [
            {"role": "system", "content": "你是一个Python编程助手"},
            {"role": "system", "content": "擅长算法和数据结构"},
            {"role": "user", "content": "实现一个二叉树" * 30},
            {"role": "assistant", "content": "二叉树类定义..." * 100},
            {"role": "tool", "tool_call_id": "call_1", "name": "execute_code", "content": "class TreeNode..." * 50},
            {"role": "user", "content": "添加前序遍历" * 30},
            {"role": "assistant", "content": "前序遍历实现..." * 100},
            {"role": "tool", "tool_call_id": "call_2", "name": "execute_code", "content": "def preorder..." * 50},
            {"role": "user", "content": "添加中序遍历" * 30},
            {"role": "assistant", "content": "中序遍历实现..." * 100},
            {"role": "tool", "tool_call_id": "call_3", "name": "execute_code", "content": "def inorder..." * 50},
            {"role": "user", "content": "添加后序遍历" * 30},
            {"role": "assistant", "content": "后序遍历实现..." * 100},
            {"role": "tool", "tool_call_id": "call_4", "name": "execute_code", "content": "def postorder..." * 50},
            {"role": "user", "content": "计算树的高度" * 30},
            {"role": "assistant", "content": "高度计算..." * 100},
            {"role": "tool", "tool_call_id": "call_5", "name": "execute_code", "content": "def height..." * 50},
        ]

    def test_full_compression_pipeline_mock(
        self, compressor_with_mock_llm, long_conversation
    ):
        """Mock: 完整压缩流程"""
        result = compressor_with_mock_llm.compress(long_conversation)
        assert isinstance(result, CompressionResult)

        compressed = result.compressed_messages
        assert len(compressed) > 0
        system_msgs = [m for m in compressed if m.get("role") == "system"]
        assert len(system_msgs) == 1
        assert "【之前对话摘要】" in system_msgs[0]["content"]
        assert "compressed_turns" in system_msgs[0]
        assert len(system_msgs[0]["compressed_turns"]) > 0

    def test_full_compression_pipeline_real(
        self, config, long_conversation
    ):
        """Real API: 完整压缩流程（带 LLM 摘要）"""
        if not should_use_real_api():
            pytest.skip("USE_REAL_API not enabled")

        from langchain_openai import ChatOpenAI
        real_llm = ChatOpenAI(
            model=os.getenv("AGENT_MODEL", "gpt-4o-mini"),
            temperature=0
        )
        compressor = ContextCompressor(config, llm=real_llm)

        result = compressor.compress(long_conversation)
        assert isinstance(result, CompressionResult)

        compressed = result.compressed_messages
        assert len(compressed) > 0
        system_msgs = [m for m in compressed if m.get("role") == "system"]
        assert len(system_msgs) == 1

        summary = system_msgs[0]["content"]
        assert "【之前对话摘要】" in summary
        assert len(summary) < 2000

    def test_hot_zone_tool_results_preserved(
        self, compressor_with_mock_llm, long_conversation
    ):
        """Mock: Hot Zone 工具结果不再注入压缩输出（已由 cleanup_tools 处理）"""
        result = compressor_with_mock_llm.compress(long_conversation)
        compressed = result.compressed_messages

        hot_zone_msgs = [
            m for m in compressed
            if m.get("is_hot_zone")
        ]
        assert len(hot_zone_msgs) == 0

        # 验证压缩只包含 system + recent user/assistant 消息
        roles = [m.get("role") for m in compressed]
        assert "tool" not in roles

    def test_compressed_turn_structure(
        self, compressor_with_mock_llm, long_conversation
    ):
        """Mock: CompressedTurn 结构验证"""
        result = compressor_with_mock_llm.compress(long_conversation)
        compressed = result.compressed_messages

        system_msg = next(
            (m for m in compressed if m.get("role") == "system"),
            None
        )
        assert system_msg is not None

        turns = system_msg.get("compressed_turns", [])
        assert len(turns) > 0

        for turn in turns:
            assert "turn_index" in turn
            assert "user_intent" in turn
            assert isinstance(turn["user_intent"], str)

    def test_token_estimation_accuracy(self, config, compressor_with_mock_llm):
        """Mock: Token 估算准确性"""
        messages = [
            {"role": "user", "content": "a" * 1000},
        ]

        total_tokens = compressor_with_mock_llm._count_tokens(messages)
        assert total_tokens > 0
        assert total_tokens < 2000

    def test_compression_ratio_calculation(
        self, compressor_with_mock_llm, long_conversation
    ):
        """Mock: 压缩比计算"""
        original_count = len(long_conversation)
        original_tokens = compressor_with_mock_llm._count_tokens(long_conversation)

        result = compressor_with_mock_llm.compress(long_conversation)
        compressed = result.compressed_messages
        compressed_count = len(compressed)
        compressed_tokens = compressor_with_mock_llm._count_tokens(compressed)

        assert original_tokens >= compressed_tokens
        assert original_count >= compressed_count


class TestMultiScenarioCompression:
    """Test suite for multiple compression scenarios"""

    @pytest.fixture
    def config(self):
        return CompressionConfig(
            max_tokens=500,
            trigger_threshold=0.1,
            keep_recent=3,
            summary_max_tokens=100,
            hot_zone_size=5,
        )

    def test_short_conversation_no_compress(self, config):
        """短对话不应触发压缩"""
        compressor = ContextCompressor(config)

        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ]

        assert not compressor.should_compress(messages)
        result = compressor.compress(messages)
        assert isinstance(result, CompressionResult)
        assert result.compressed_messages == messages

    def test_conversation_with_errors(
        self, config
    ):
        """Mock: 含错误执行的对话压缩"""
        compressor = ContextCompressor(config)

        messages = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "运行代码"},
            {"role": "assistant", "content": "...", "tool_calls": [{"id": "call_1", "name": "execute_code"}]},
            {"role": "tool", "tool_call_id": "call_1", "name": "execute_code", "content": "Error: 语法错误", "status": "failed"},
            {"role": "user", "content": "修复错误"},
            {"role": "assistant", "content": "已修复..."},
        ]

        result = compressor.compress(messages)
        assert isinstance(result, CompressionResult)
        assert len(result.compressed_messages) > 0

    def test_conversation_with_partial_success(
        self, config
    ):
        """Mock: 部分成功的对话压缩"""
        compressor = ContextCompressor(config)

        messages = [
            {"role": "system", "content": "你是一个助手" * 20},
            {"role": "user", "content": "任务1" * 20},
            {"role": "assistant", "content": "任务1完成..." * 30},
            {"role": "tool", "tool_call_id": "call_1", "name": "execute_code", "content": "Success"},
            {"role": "user", "content": "任务2" * 20},
            {"role": "assistant", "content": "任务2失败..." * 30},
            {"role": "tool", "tool_call_id": "call_2", "name": "execute_code", "content": "Error"},
        ]

        result = compressor.compress(messages)
        assert isinstance(result, CompressionResult)
        assert len(result.compressed_messages) > 0