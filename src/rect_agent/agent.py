import logging
from typing import Any, Callable

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import create_react_agent

from src.agent.config import AgentConfig, DEFAULT_CONFIG
from src.agent.context.long_term import LongTermManager, LongTermConfig
from src.agent.context.compression import ContextCompressor, CompressionConfig
from src.agent.rate_limiter import get_tool_breakers

from src.rect_agent.state import RectAgentState
from src.rect_agent.tools.wrapper import build_tool_node
from src.rect_agent.hooks.prompt import build_prompt_fn
from src.rect_agent.hooks.pre_model import build_pre_model_hook
from src.rect_agent.hooks.post_model import build_post_model_hook

logger = logging.getLogger(__name__)


class RectAgent:
    def __init__(
        self,
        config: AgentConfig = DEFAULT_CONFIG,
        llm=None,
        callback: Callable | None = None,
    ):
        self.config = config
        self.llm = llm
        self.callback = callback

        long_term_config = LongTermConfig(
            memory_dir=config.long_term.memory_dir,
            session_ttl_days=config.long_term.session_ttl_days,
            vector_enabled=config.long_term.vector_enabled,
            chroma_persist_dir=config.long_term.chroma_persist_dir,
        )
        self.long_term = LongTermManager(long_term_config)

        compression_config = CompressionConfig(
            trigger_threshold=config.short_term.trigger_threshold,
            keep_recent=config.short_term.keep_recent,
        )
        self.compressor = ContextCompressor(compression_config, llm)

        redis_url = config.long_term.redis_url
        if redis_url:
            get_tool_breakers(redis_url=redis_url)

        self._graph = None

    def _build_graph(self, checkpointer: SqliteSaver | None = None):
        tool_node = build_tool_node()
        prompt_fn = build_prompt_fn(long_term=self.long_term)
        pre_hook = build_pre_model_hook(long_term=self.long_term, compressor=self.compressor)
        post_hook = build_post_model_hook(long_term=self.long_term)

        agent = create_react_agent(
            model=self.llm,
            tools=tool_node,
            prompt=prompt_fn,
            pre_model_hook=pre_hook,
            post_model_hook=post_hook,
            state_schema=RectAgentState,
            checkpointer=checkpointer,
            version="v2",
            name="rect_agent",
        )
        return agent

    def compile(self, checkpointer: SqliteSaver | None = None):
        self._graph = self._build_graph(checkpointer=checkpointer)
        return self._graph

    def invoke(self, input_data: dict, config: dict | None = None):
        if self._graph is None:
            self.compile()
        return self._graph.invoke(input_data, config or {})

    def stream(self, input_data: dict, config: dict | None = None):
        if self._graph is None:
            self.compile()
        yield from self._graph.stream(input_data, config or {})


def create_rect_agent(
    config: AgentConfig = DEFAULT_CONFIG,
    llm=None,
    callback: Callable | None = None,
) -> RectAgent:
    return RectAgent(config=config, llm=llm, callback=callback)
