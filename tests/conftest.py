import pytest
import os
import sys
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Generator


def should_use_real_api() -> bool:
    """检查是否使用真实 API"""
    return os.getenv("USE_REAL_API", "false").lower() == "true"


def is_windows() -> bool:
    return sys.platform == "win32"


@pytest.fixture(scope="session")
def test_env() -> dict:
    """测试环境信息"""
    return {
        "use_real_api": should_use_real_api(),
        "is_windows": is_windows(),
        "python_version": sys.version,
        "platform": sys.platform,
    }


def _create_mock_llm():
    """创建 Mock LLM"""
    llm = MagicMock()

    def mock_invoke(messages, **kwargs):
        response = MagicMock()
        response.content = "这是 AI 的回复"
        response.response_metadata = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
        return response

    llm.invoke.side_effect = mock_invoke
    return llm


def create_mock_llm_with_response(response_content: str, tool_calls: list = None):
    """创建自定义响应的 Mock LLM"""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = response_content
    mock_response.response_metadata = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
    }
    if tool_calls:
        mock_response.tool_calls = tool_calls
    mock_llm.invoke.return_value = mock_response
    return mock_llm


@pytest.fixture
def llm():
    """根据 USE_REAL_API 环境变量返回 Mock 或 Real LLM"""
    if should_use_real_api():
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=os.getenv("AGENT_MODEL", "openai:gpt-4o-mini"),
                temperature=0
            )
        except ImportError:
            pytest.skip("langchain_openai not installed")
    else:
        return _create_mock_llm()


@pytest.fixture
def mock_llm():
    """强制使用 Mock LLM"""
    return _create_mock_llm()


@pytest.fixture
def real_llm_required():
    """跳过标记 - Real API 专用测试"""
    if not should_use_real_api():
        pytest.skip("Requires USE_REAL_API=true")
    try:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.getenv("AGENT_MODEL", "openai:gpt-4o-mini"),
            temperature=0
        )
    except ImportError:
        pytest.skip("langchain_openai not installed")


@pytest.fixture
def temp_memory_dir(tmp_path) -> str:
    """创建临时 memory 目录"""
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    (mem_dir / "sessions").mkdir()
    (mem_dir / "chroma").mkdir()
    (mem_dir / "archive").mkdir()
    return str(mem_dir)


@pytest.fixture
def mock_env_vars(temp_memory_dir: str) -> dict:
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
def mock_config(mock_env_vars: dict):
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
def agent(mock_config, mock_llm, mock_env_vars):
    """创建 Agent 实例"""
    with patch("src.agent.context.long_term.chromadb"):
        from src.agent.agent import create_agent
        return create_agent(
            model="openai:gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
        )


@pytest.fixture
def agent_with_real_api(temp_memory_dir):
    """创建真实 API Agent 实例"""
    if not should_use_real_api():
        pytest.skip("Requires USE_REAL_API=true")

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
        agent.config.long_term.memory_dir = temp_memory_dir
        agent.config.long_term.chroma_persist_dir = f"{temp_memory_dir}/chroma"
        agent.config.long_term.vector_enabled = False
        return agent


@pytest.fixture(autouse=True)
def setup_logging():
    """自动设置测试日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    yield


@pytest.fixture
def mock_chroma():
    """Mock ChromaDB 避免单例状态污染"""
    with patch("src.agent.context.long_term.chromadb") as mock:
        yield mock


@pytest.fixture
def assert_response_valid():
    """验证 Agent 响应格式的辅助函数"""
    def _assert(response: dict, require_messages: bool = True):
        assert response is not None, "Response cannot be None"
        assert "status" in response, "Response must have 'status' field"
        assert response["status"] in ["success", "error"], f"Invalid status: {response['status']}"
        if require_messages:
            assert "messages" in response, "Response must have 'messages' field"
    return _assert