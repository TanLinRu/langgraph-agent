"""Tests for tool result L3 persistence"""
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

import pytest

from src.agent.context.long_term import LongTermManager, LongTermConfig


def should_use_real_api():
    return os.getenv("USE_REAL_API", "false").lower() == "true"


@pytest.fixture
def memory_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def long_term(memory_dir):
    config = LongTermConfig(
        memory_dir=memory_dir,
        vector_enabled=False,
    )
    mgr = LongTermManager(config)
    yield mgr
    mgr.close()


@pytest.mark.unit
@pytest.mark.context
class TestToolResultPersistence:
    """Test suite for tool result L3 persistence"""

    def test_save_and_load(self, long_term):
        """保存和加载单个 tool result"""
        results = [{
            "tool_call_id": "call_abc123",
            "tool_name": "execute_code",
            "content": "print('hello world')",
            "status": "success",
            "metadata": "{}",
        }]
        long_term.save_tool_results("thread_1", results)

        loaded = long_term.load_tool_result("thread_1", "call_abc123")
        assert loaded is not None
        assert loaded["tool_name"] == "execute_code"
        assert loaded["content"] == "print('hello world')"
        assert loaded["status"] == "success"

    def test_save_and_load_multiple(self, long_term):
        """批量保存和加载"""
        results = [
            {"tool_call_id": f"call_{i}", "tool_name": "read_file",
             "content": f"content_{i}", "status": "success", "metadata": "{}"}
            for i in range(5)
        ]
        long_term.save_tool_results("thread_1", results)

        for i in range(5):
            loaded = long_term.load_tool_result("thread_1", f"call_{i}")
            assert loaded["content"] == f"content_{i}"

    def test_load_nonexistent(self, long_term):
        """加载不存在的记录返回 None"""
        loaded = long_term.load_tool_result("thread_1", "nonexistent")
        assert loaded is None

    def test_load_by_thread(self, long_term):
        """按线程加载所有 tool results"""
        results_1 = [
            {"tool_call_id": "call_a", "tool_name": "read_file",
             "content": "a", "status": "success", "metadata": "{}"}
        ]
        results_2 = [
            {"tool_call_id": "call_b", "tool_name": "write_file",
             "content": "b", "status": "success", "metadata": "{}"}
        ]
        long_term.save_tool_results("thread_a", results_1)
        long_term.save_tool_results("thread_b", results_2)

        loaded_a = long_term.load_tool_results_by_thread("thread_a")
        assert len(loaded_a) == 1
        assert loaded_a[0]["tool_call_id"] == "call_a"

        loaded_b = long_term.load_tool_results_by_thread("thread_b")
        assert len(loaded_b) == 1
        assert loaded_b[0]["tool_call_id"] == "call_b"

    def test_search_by_tool_name(self, long_term):
        """按工具名搜索"""
        results = [
            {"tool_call_id": "call_1", "tool_name": "execute_code",
             "content": "def foo(): pass", "status": "success", "metadata": "{}"},
            {"tool_call_id": "call_2", "tool_name": "read_file",
             "content": "import os", "status": "success", "metadata": "{}"},
            {"tool_call_id": "call_3", "tool_name": "execute_code",
             "content": "print('hello')", "status": "success", "metadata": "{}"},
        ]
        long_term.save_tool_results("thread_1", results)

        found = long_term.search_tool_results("thread_1", "execute_code")
        assert len(found) >= 2
        assert all("execute" in r["tool_name"] for r in found)

    def test_search_by_content(self, long_term):
        """按内容搜索"""
        results = [
            {"tool_call_id": "call_1", "tool_name": "execute_code",
             "content": "print('hello world')", "status": "success", "metadata": "{}"},
        ]
        long_term.save_tool_results("thread_1", results)

        found = long_term.search_tool_results("thread_1", "hello")
        assert len(found) >= 1
