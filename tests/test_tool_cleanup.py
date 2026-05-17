"""Tests for tool result cleanup + read_tool_detail tool"""
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

import pytest

from src.agent.state import create_initial_state, AgentState
from src.agent.tools import read_tool_detail, set_tool_result_manager


def should_use_real_api():
    return os.getenv("USE_REAL_API", "false").lower() == "true"


def make_tool_msg(tool_call_id: str, name: str, content: str, status="success"):
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": content,
        "status": status,
    }


@pytest.fixture
def mock_long_term():
    """模拟 LongTermManager"""
    from src.agent.context.long_term import LongTermManager, LongTermConfig
    with tempfile.TemporaryDirectory() as tmp:
        mgr = LongTermManager(LongTermConfig(memory_dir=Path(tmp), vector_enabled=False))
        set_tool_result_manager(mgr)
        yield mgr
        mgr.close()


@pytest.mark.unit
@pytest.mark.context
class TestToolCleanup:
    """Test suite for tool cleanup logic"""

    def test_cleanup_removes_tool_messages(self):
        """_node_cleanup_tools 应该移除 tool 消息"""
        from src.agent.agent import Agent
        from src.agent.config import DEFAULT_CONFIG

        agent = Agent(config=DEFAULT_CONFIG, enable_tracing=False)

        state = create_initial_state("test_cleanup")
        tool_msgs = [
            make_tool_msg("call_1", "execute_code", "result_1"),
            make_tool_msg("call_2", "read_file", "result_2"),
        ]
        state["messages"] = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ] + tool_msgs

        result = agent._node_cleanup_tools(state)
        assert result is not None
        new_messages = result.get("messages", [])
        new_tool_msgs = [m for m in new_messages if m.get("role") == "tool"]
        assert len(new_tool_msgs) == len(tool_msgs)  # 不超过 keep_recent 则保留

    def test_cleanup_persists_to_l3(self):
        """超过 keep_recent 的 tool 结果应持久化到 L3"""
        from src.agent.agent import Agent
        from src.agent.config import DEFAULT_CONFIG

        agent = Agent(config=DEFAULT_CONFIG, enable_tracing=False)

        state = create_initial_state("test_persist")
        tool_msgs = [
            make_tool_msg(f"call_{i}", "execute_code", f"result_{i}")
            for i in range(20)
        ]
        state["messages"] = [
            {"role": "user", "content": "hello"},
        ] + tool_msgs

        result = agent._node_cleanup_tools(state)
        new_messages = result.get("messages", [])
        new_tool_msgs = [m for m in new_messages if m.get("role") == "tool"]

        # 只有 keep_recent 条保留
        keep_count = agent.config.short_term.keep_recent
        assert len(new_tool_msgs) <= keep_count

    def test_hot_tool_results_updated(self):
        """hot_tool_results 应包含最新 tool 摘要"""
        from src.agent.agent import Agent
        from src.agent.config import DEFAULT_CONFIG

        agent = Agent(config=DEFAULT_CONFIG, enable_tracing=False)

        state = create_initial_state("test_hot")
        tool_msgs = [
            make_tool_msg("call_hot", "execute_code", "hot_result_content"),
        ]
        state["messages"] = [
            {"role": "user", "content": "hello"},
        ] + tool_msgs

        result = agent._node_cleanup_tools(state)
        hot_results = result.get("hot_tool_results", [])
        assert len(hot_results) >= 1
        assert hot_results[0]["tool_call_id"] == "call_hot"
        assert hot_results[0]["is_hot"] is True


@pytest.mark.unit
@pytest.mark.context
class TestReadToolDetail:
    """Test suite for read_tool_detail tool"""

    def test_read_existing_result(self, mock_long_term):
        """读取已持久化的 tool result"""
        mock_long_term.save_tool_results("thread_test", [{
            "tool_call_id": "call_xyz",
            "tool_name": "execute_code",
            "content": "print('hello world')",
            "status": "success",
            "metadata": "{}",
        }])

        result = read_tool_detail.invoke({
            "thread_id": "thread_test",
            "tool_call_id": "call_xyz",
        })
        assert "execute_code" in result
        assert "print('hello world')" in result

    def test_read_nonexistent(self, mock_long_term):
        """读取不存在的记录"""
        result = read_tool_detail.invoke({
            "thread_id": "thread_test",
            "tool_call_id": "call_missing",
        })
        assert "未找到" in result

    def test_read_truncates_long_content(self, mock_long_term):
        """超长内容截断"""
        long_content = "x" * 10000
        mock_long_term.save_tool_results("thread_test", [{
            "tool_call_id": "call_long",
            "tool_name": "execute_code",
            "content": long_content,
            "status": "success",
            "metadata": "{}",
        }])

        result = read_tool_detail.invoke({
            "thread_id": "thread_test",
            "tool_call_id": "call_long",
        })
        # 应包含截断提示
        assert "仅显示前 8000" in result
        # 不应包含全部 10000 字符
        assert len(result) < 9500
