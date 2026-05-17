"""Tests for user profile system"""
import os
import json
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from src.agent.schemas import UserProfile
from src.agent.context.long_term import LongTermManager, LongTermConfig


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


@pytest.fixture
def sample_profile():
    return UserProfile(
        user_id="user_1",
        tenant_id="tenant_1",
        org_id="org_1",
        preferences={"language": "python", "verbose": False, "auto_execute": True},
        known_context=["熟悉 LangGraph", "用过 FastAPI"],
        behavior_patterns={
            "avg_turns_per_session": 3.5,
            "tool_usage_ratio": 0.7,
            "total_sessions": 12,
            "common_tools": ["execute_code", "read_file"],
        },
    )


@pytest.mark.unit
@pytest.mark.context
class TestUserProfileModel:
    """Test suite for UserProfile data model"""

    def test_creation_defaults(self):
        """默认字段验证"""
        profile = UserProfile(user_id="test_user")
        assert profile.user_id == "test_user"
        assert profile.preferences["language"] == "python"
        assert profile.known_context == []
        assert profile.behavior_patterns["total_sessions"] == 0

    def test_to_system_block_with_data(self, sample_profile):
        """非空画像生成 system block"""
        block = sample_profile.to_system_block()
        assert "## 用户画像" in block
        assert "熟悉 LangGraph" in block
        assert "verbose: False" in block
        assert "language: python" in block

    def test_to_system_block_empty(self):
        """空画像返回空字符串"""
        profile = UserProfile(user_id="empty", known_context=[], preferences={})
        assert profile.to_system_block() == ""

    def test_to_system_block_only_context(self):
        """仅含背景信息"""
        profile = UserProfile(user_id="test", known_context=["熟悉 Python"], preferences={})
        block = profile.to_system_block()
        assert "熟悉 Python" in block
        assert "偏好设置" not in block


@pytest.mark.unit
@pytest.mark.context
class TestUserProfilePersistence:
    """Test suite for profile save/load"""

    def test_save_and_load(self, long_term, sample_profile):
        """保存和加载用户画像"""
        long_term.save_user_profile(sample_profile)
        loaded = long_term.load_user_profile("user_1", "tenant_1", "org_1")
        assert loaded is not None
        assert loaded.user_id == "user_1"
        assert loaded.preferences["language"] == "python"
        assert "熟悉 LangGraph" in loaded.known_context
        assert loaded.behavior_patterns["total_sessions"] == 12

    def test_load_nonexistent(self, long_term):
        """加载不存在的画像返回 None"""
        loaded = long_term.load_user_profile("nonexistent_user")
        assert loaded is None

    def test_update_existing(self, long_term, sample_profile):
        """更新已有画像"""
        long_term.save_user_profile(sample_profile)

        updated = UserProfile(
            user_id="user_1",
            tenant_id="tenant_1",
            org_id="org_1",
            known_context=["熟悉 LangGraph", "熟悉 FastAPI", "熟悉 Docker"],
        )
        long_term.save_user_profile(updated)

        loaded = long_term.load_user_profile("user_1", "tenant_1", "org_1")
        assert len(loaded.known_context) == 3
        assert "熟悉 Docker" in loaded.known_context

    def test_tenant_isolation(self, long_term, sample_profile):
        """不同租户隔离"""
        long_term.save_user_profile(sample_profile)

        # 不同租户
        loaded = long_term.load_user_profile("user_1", "tenant_2", "org_1")
        assert loaded is None

    def test_last_updated_set_on_save(self, long_term, sample_profile):
        """保存时自动设置 last_updated"""
        long_term.save_user_profile(sample_profile)
        loaded = long_term.load_user_profile("user_1", "tenant_1", "org_1")
        assert loaded.last_updated != ""


@pytest.mark.unit
@pytest.mark.context
class TestProfileInjection:
    """Test suite for profile injection into system message"""

    def test_inject_into_system_msg(self, sample_profile):
        """画像注入到 system message"""
        from src.agent.agent import Agent
        from src.agent.config import DEFAULT_CONFIG

        agent = Agent(config=DEFAULT_CONFIG, enable_tracing=False)
        # 通过 Agent 自己的 long_term 保存画像
        agent.long_term.save_user_profile(sample_profile)

        messages = [{"role": "system", "content": "System prompt"}]
        state = {
            "messages": messages,
            "user_id": "user_1",
            "tenant_id": "tenant_1",
            "org_id": "org_1",
        }

        result = agent._node_inject_profile(state)
        assert result is not None
        new_messages = result.get("messages", [])
        assert len(new_messages) == 1
        assert "## 用户画像" in new_messages[0]["content"]
        assert "熟悉 LangGraph" in new_messages[0]["content"]

    def test_no_profile_returns_empty(self):
        """无画像时返回空 dict"""
        from src.agent.agent import Agent
        from src.agent.config import DEFAULT_CONFIG

        agent = Agent(config=DEFAULT_CONFIG, enable_tracing=False)

        messages = [{"role": "system", "content": "System prompt"}]
        state = {
            "messages": messages,
            "user_id": "nonexistent",
            "tenant_id": "default",
            "org_id": "default",
        }

        result = agent._node_inject_profile(state)
        assert result == {}  # 无修改

    def test_no_system_msg_no_injection(self, sample_profile):
        """无 system 消息时不注入（消息原样返回）"""
        from src.agent.agent import Agent
        from src.agent.config import DEFAULT_CONFIG

        agent = Agent(config=DEFAULT_CONFIG, enable_tracing=False)
        agent.long_term.save_user_profile(sample_profile)

        state = {
            "messages": [{"role": "user", "content": "hello"}],
            "user_id": "user_1",
            "tenant_id": "tenant_1",
            "org_id": "org_1",
        }

        result = agent._node_inject_profile(state)
        # 有画像但无 system msg → 消息原样返回
        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0]["content"] == "hello"

    def test_empty_profile_block_no_injection(self):
        """空的画像 block 不注入"""
        empty_profile = UserProfile(user_id="empty_user", known_context=[], preferences={})

        from src.agent.agent import Agent
        from src.agent.config import DEFAULT_CONFIG

        agent = Agent(config=DEFAULT_CONFIG, enable_tracing=False)
        agent.long_term.save_user_profile(empty_profile)

        messages = [{"role": "system", "content": "System prompt"}]
        state = {
            "messages": messages,
            "user_id": "empty_user",
            "tenant_id": "default",
            "org_id": "default",
        }

        result = agent._node_inject_profile(state)
        assert result == {}
