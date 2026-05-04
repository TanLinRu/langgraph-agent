import pytest
import os
import sys
from unittest.mock import MagicMock, patch

@pytest.fixture
def temp_memory_dir(tmp_path):
    """创建临时 memory 目录"""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    (mem_dir / "sessions").mkdir()
    (mem_dir / "archive").mkdir()
    return str(mem_dir)


@pytest.fixture
def mock_env_vars(temp_memory_dir):
    """Mock 环境变量"""
    env = {
        "OPENAI_API_KEY": "test-key",
        "AGENT_MEMORY_DIR": temp_memory_dir,
        "AGENT_MODEL": "openai:gpt-4o-mini",
        "AGENT_SESSION_TTL_DAYS": "7",
    }
    with patch.dict(os.environ, env, clear=True):
        yield env


@pytest.fixture
def mock_config(mock_env_vars):
    """创建 Mock 配置"""
    with patch("src.agent.config.DEFAULT_CONFIG") as config:
        config.model = "openai:gpt-4o-mini"
        config.api_key = "test-key"
        config.base_url = "https://api.openai.com/v1"
        config.short_term.trigger_threshold = 0.7
        config.short_term.keep_recent = 5
        config.long_term.memory_dir = mock_env_vars["AGENT_MEMORY_DIR"]
        config.long_term.session_ttl_days = 7
        config.long_term.vector_enabled = False
        config.long_term.chroma_persist_dir = f"{mock_env_vars['AGENT_MEMORY_DIR']}/chroma"
        config.initialization.resume_on_startup = False
        config.initialization.load_recent_sessions = 5
        config.initialization.load_memory = False
        yield config


@pytest.fixture
def mock_llm():
    """创建 Mock LLM"""
    llm = MagicMock()

    def mock_invoke(messages, **kwargs):
        last = messages[-1] if messages else {}
        response = MagicMock()
        response.content = "这是 AI 的回复"
        response.response_metadata = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
        return response

    llm.invoke.side_effect = mock_invoke
    return llm


@pytest.fixture
def agent(mock_config, mock_llm, mock_env_vars):
    """创建 Agent 实例"""
    from src.agent.agent import Agent, create_agent
    return create_agent(
        model="openai:gpt-4o-mini",
        api_key="test-key",
        base_url="https://api.openai.com/v1",
    )
