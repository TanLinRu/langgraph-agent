"""Tests for real multi-turn conversation flows"""
import os
from unittest.mock import patch, MagicMock

import pytest


def should_use_real_api():
    return os.getenv("USE_REAL_API", "false").lower() == "true"


class TestMultiTurnConversation:
    """Test suite for multi-turn conversation flows"""

    @pytest.fixture
    def real_agent(self, tmp_path):
        """创建真实 Agent 实例"""
        if not should_use_real_api():
            pytest.skip("USE_REAL_API not enabled")

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        with patch("src.agent.context.long_term.chromadb"):
            from src.agent.agent import create_agent

            agent = create_agent(
                model=os.getenv("AGENT_MODEL", "openai:gpt-4o-mini"),
                api_key=api_key,
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            )

            agent.config.long_term.memory_dir = tmp_path / "memory"
            agent.config.long_term.chroma_persist_dir = str(tmp_path / "memory/chroma")
            agent.config.long_term.vector_enabled = False

            return agent

    @pytest.fixture
    def mock_agent(self, tmp_path):
        """创建 Mock Agent 实例"""
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
                "content": "Mock response",
                "tool_calls": [],
            }
            agent.llm = mock_llm

            return agent

    def test_single_turn_mock(self, mock_agent, tmp_path):
        """Mock: 单轮对话"""
        thread_id = "test-single-mock"

        result = mock_agent.run("你好", thread_id=thread_id)
        assert result["status"] == "success"
        assert "result" in result or "messages" in result

    def test_single_turn_real(self, real_agent, tmp_path):
        """Real API: 单轮对话"""
        thread_id = "test-single-real"

        result = real_agent.run("你好，帮我实现一个简单的加法函数", thread_id=thread_id)
        assert result["status"] == "success"
        assert len(result.get("messages", [])) > 0

    def test_two_turn_conversation_mock(self, mock_agent, tmp_path):
        """Mock: 两轮对话"""
        thread_id = "test-two-turn-mock"

        result1 = mock_agent.run("你好", thread_id=thread_id)
        assert result1["status"] == "success"

        result2 = mock_agent.run("今天天气如何？", thread_id=thread_id)
        assert result2["status"] == "success"

        assert mock_agent.llm.invoke.call_count >= 2

    def test_two_turn_conversation_real(self, real_agent, tmp_path):
        """Real API: 两轮对话"""
        thread_id = "test-two-turn-real"

        result1 = real_agent.run("我叫张三", thread_id=thread_id)
        assert result1["status"] == "success"

        result2 = real_agent.run("我叫什么名字？", thread_id=thread_id)
        assert result2["status"] == "success"

        response_text = result2.get("messages", [])[-1].get("content", "")
        assert "张三" in response_text or "记得" in response_text

    def test_code_generation_flow_mock(self, mock_agent, tmp_path):
        """Mock: 代码生成流程"""
        thread_id = "test-code-gen-mock"

        result = mock_agent.run("用 Python 实现快速排序", thread_id=thread_id)
        assert result["status"] == "success"

    def test_code_generation_flow_real(self, real_agent, tmp_path):
        """Real API: 代码生成流程"""
        thread_id = "test-code-gen-real"

        result = real_agent.run(
            "用 Python 实现一个函数，计算斐波那契数列的第n项",
            thread_id=thread_id
        )
        assert result["status"] == "success"

        response_text = result.get("messages", [])[-1].get("content", "")
        assert len(response_text) > 0

    def test_context_window_behavior_mock(self, mock_agent, tmp_path):
        """Mock: 上下文窗口行为"""
        thread_id = "test-context-mock"

        long_content = "详细描述一个复杂的算法需求：" + "这是需求描述。" * 100
        result = mock_agent.run(long_content, thread_id=thread_id)
        assert result["status"] == "success"

    def test_context_window_behavior_real(self, real_agent, tmp_path):
        """Real API: 上下文窗口行为（长输入）"""
        thread_id = "test-context-real"

        long_content = (
            "请帮我实现一个完整的用户管理系统，包含以下功能：\n"
            "1. 用户注册\n"
            "2. 用户登录\n"
            "3. 用户信息查询\n"
            "4. 用户权限管理\n"
            "5. 密码修改\n"
            "6. 会话管理\n"
            "请使用 Python 实现，代码要完整可运行。"
        ) * 3

        result = real_agent.run(long_content, thread_id=thread_id)
        assert result["status"] == "success"

    def test_multi_turn_with_code_execution_mock(self, mock_agent, tmp_path):
        """Mock: 带代码执行的多轮对话"""
        thread_id = "test-code-exec-mock"

        result1 = mock_agent.run("写一个计算阶乘的函数", thread_id=thread_id)
        assert result1["status"] == "success"

        result2 = mock_agent.run("测试一下，计算5的阶乘", thread_id=thread_id)
        assert result2["status"] == "success"

    def test_multi_turn_with_code_execution_real(self, real_agent, tmp_path):
        """Real API: 带代码执行的多轮对话"""
        thread_id = "test-code-exec-real"

        result1 = real_agent.run("用 Python 写一个计算列表平均值的函数", thread_id=thread_id)
        assert result1["status"] == "success"

        result2 = real_agent.run("测试一下 [1, 2, 3, 4, 5]", thread_id=thread_id)
        assert result2["status"] == "success"

        response_text = result2.get("messages", [])[-1].get("content", "")
        assert "3" in response_text or "平均" in response_text

    def test_error_recovery_flow_mock(self, mock_agent, tmp_path):
        """Mock: 错误恢复流程"""
        thread_id = "test-error-mock"

        result1 = mock_agent.run("故意执行一个有错误的代码", thread_id=thread_id)
        assert result1["status"] == "success"

        result2 = mock_agent.run("请修复错误", thread_id=thread_id)
        assert result2["status"] == "success"

    def test_session_persistence_mock(self, mock_agent, tmp_path):
        """Mock: 会话持久化"""
        thread_id = "test-persist-mock"

        result1 = mock_agent.run("记住我喜欢蓝色", thread_id=thread_id)
        assert result1["status"] == "success"

        result2 = mock_agent.run("我刚才说我喜欢什么颜色？", thread_id=thread_id)
        assert result2["status"] == "success"

    def test_session_persistence_real(self, real_agent, tmp_path):
        """Real API: 会话持久化"""
        thread_id = "test-persist-real"

        result1 = real_agent.run("记住我的名字是李四", thread_id=thread_id)
        assert result1["status"] == "success"

        result2 = real_agent.run("我叫什么名字？", thread_id=thread_id)
        assert result2["status"] == "success"

        response_text = result2.get("messages", [])[-1].get("content", "")
        assert "李四" in response_text or "记得" in response_text


class TestConversationScenarios:
    """Test suite for specific conversation scenarios"""

    @pytest.fixture
    def scenario_agent(self, tmp_path):
        """创建 Agent 实例（Mock）"""
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
                "content": "Scenario response",
                "tool_calls": [],
            }
            agent.llm = mock_llm

            return agent

    def test_conversation_topic_switch(self, scenario_agent, tmp_path):
        """Mock: 话题切换"""
        thread_id = "test-topic-switch"

        result1 = scenario_agent.run("我们讨论Python编程", thread_id=thread_id)
        assert result1["status"] == "success"

        result2 = scenario_agent.run("现在切换到JavaScript", thread_id=thread_id)
        assert result2["status"] == "success"

        assert scenario_agent.llm.invoke.call_count == 2

    def test_conversation_continuation(self, scenario_agent, tmp_path):
        """Mock: 对话继续"""
        thread_id = "test-continue"

        scenario_agent.run("开始一个新项目", thread_id=thread_id)
        scenario_agent.run("添加用户管理模块", thread_id=thread_id)
        scenario_agent.run("添加日志记录功能", thread_id=thread_id)

        assert scenario_agent.llm.invoke.call_count == 3

    def test_conversation_abstraction(self, scenario_agent, tmp_path):
        """Mock: 对话抽象（压缩后）"""
        thread_id = "test-abstract"

        for i in range(5):
            scenario_agent.run(f"任务{i}：实现某个功能", thread_id=thread_id)

        assert scenario_agent.llm.invoke.call_count == 5