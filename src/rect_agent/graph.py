"""
LangGraph Studio 兼容图定义

与 src/rect_agent/agent.py 共享逻辑，但：
- 无 checkpointer（由 Studio 管理）
- 无 post_model_hook（简化持久化）
- 保留 pre_model_hook 用于正确率和记忆检索
"""
"""
LangGraph Studio 可视化入口
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.agent.config import DEFAULT_CONFIG
from src.agent.context.long_term import LongTermManager, LongTermConfig
from src.agent.context.compression import ContextCompressor, CompressionConfig

from src.rect_agent.state import RectAgentState
from src.rect_agent.tools.wrapper import build_tool_node
from src.rect_agent.hooks.prompt import build_prompt_fn
from src.rect_agent.hooks.pre_model import build_pre_model_hook

logger = logging.getLogger(__name__)

config = DEFAULT_CONFIG.model_copy(update={
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model": os.getenv("AGENT_MODEL", "openai:gpt-4"),
})

llm = ChatOpenAI(
    model=config.model.replace("openai:", ""),
    api_key=config.api_key,
    base_url=config.base_url,
    temperature=0,
)

long_term_config = LongTermConfig(
    memory_dir=config.long_term.memory_dir,
    session_ttl_days=config.long_term.session_ttl_days,
    vector_enabled=config.long_term.vector_enabled,
    chroma_persist_dir=config.long_term.chroma_persist_dir,
)
long_term = LongTermManager(long_term_config)

compression_config = CompressionConfig(
    trigger_threshold=config.short_term.trigger_threshold,
    keep_recent=config.short_term.keep_recent,
)
compressor = ContextCompressor(compression_config, llm)

tool_node = build_tool_node()
prompt_fn = build_prompt_fn(long_term=long_term)
pre_hook = build_pre_model_hook(long_term=long_term, compressor=compressor)

agent = create_react_agent(
    model=llm,
    tools=tool_node,
    prompt=prompt_fn,
    pre_model_hook=pre_hook,
    state_schema=RectAgentState,
    version="v2",
    name="rect_agent_studio",
)

graph = agent.compile()
