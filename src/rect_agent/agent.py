import logging
from typing import Any, Callable, Generic, TypeVar

from pydantic import BaseModel

from langchain_core.runnables import Runnable
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import create_react_agent

from src.agent.config import AgentConfig, DEFAULT_CONFIG
from src.agent.context.long_term import LongTermManager, LongTermConfig
from src.agent.context.compression import ContextCompressor, CompressionConfig
from src.agent.graceful_degradation import ServiceHealthChecker
from src.agent.rate_limiter import get_tool_breakers
from src.agent.schemas.agent_protocol import StructuredAgentError, ErrorLevel

from src.rect_agent.state import RectAgentState
from src.rect_agent.tools.wrapper import build_tool_node
from src.rect_agent.hooks.prompt import build_prompt_fn
from src.rect_agent.hooks.pre_model import build_pre_model_hook
from src.rect_agent.hooks.post_model import build_post_model_hook

logger = logging.getLogger(__name__)

OutputT = TypeVar("OutputT", bound="BaseModel | str")


class RectAgent(Generic[OutputT]):
    def __init__(
        self,
        config: AgentConfig = DEFAULT_CONFIG,
        llm=None,
        callback: Callable | None = None,
        output_type: type[OutputT] = str,
    ):
        self.config = config
        self.llm = llm
        self.callback = callback
        self._output_schema = output_type

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

        self.health_checker = ServiceHealthChecker()
        self._graph = None

    def _build_llm_with_breaker(self):
        retry_llm = self.llm.with_retry(
            stop_after_attempt=4,
            retry_if_exception_type=(TimeoutError, ConnectionError),
        )

        class _BreakerWrapper(Runnable):
            def __init__(inner_self):
                inner_self._retry_llm = retry_llm
                inner_self._original = self.llm

            def bind_tools(inner_self, tools, **kwargs):
                inner_self._original.bind_tools(tools, **kwargs)
                return inner_self

            def invoke(inner_self, input, config=None, **kwargs):
                if not get_tool_breakers().get_breaker("_llm").can_execute():
                    raise StructuredAgentError(
                        error_code="LLM_CIRCUIT_OPEN", error_type="RECOVERABLE",
                        message="LLM \u7194\u65ad\u5668\u5f00\u542f", retryable=False,
                        error_level=ErrorLevel.HIGH,
                    )
                return inner_self._retry_llm.invoke(input, config, **kwargs)

            def stream(inner_self, input, config=None, **kwargs):
                if not get_tool_breakers().get_breaker("_llm").can_execute():
                    raise StructuredAgentError(
                        error_code="LLM_CIRCUIT_OPEN", error_type="RECOVERABLE",
                        message="LLM \u7194\u65ad\u5668\u5f00\u542f", retryable=False,
                        error_level=ErrorLevel.HIGH,
                    )
                return inner_self._retry_llm.stream(input, config, **kwargs)

        return _BreakerWrapper()

    def _build_graph(self, checkpointer: SqliteSaver | None = None):
        tool_node = build_tool_node()
        prompt_fn = build_prompt_fn(long_term=self.long_term)
        pre_hook = build_pre_model_hook(long_term=self.long_term, compressor=self.compressor, health_checker=self.health_checker)
        post_hook = build_post_model_hook(long_term=self.long_term)

        model = self._build_llm_with_breaker() if hasattr(self.llm, "with_retry") else self.llm
        agent = create_react_agent(
            model=model,
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

    def invoke(self, input_data: dict, config: dict | None = None) -> OutputT:
        if self._graph is None:
            self.compile()
        result = self._graph.invoke(input_data, config or {})
        messages = result.get("messages", [])
        if not messages:
            return result  # type: ignore
        last = messages[-1]
        content = getattr(last, "content", "") or ""
        if self._output_schema is str:
            return content  # type: ignore
        return self._output_schema.model_validate_json(content)

    def stream(self, input_data: dict, config: dict | None = None):
        if self._graph is None:
            self.compile()
        yield from self._graph.stream(input_data, config or {})


def create_rect_agent(
    config: AgentConfig = DEFAULT_CONFIG,
    llm=None,
    callback: Callable | None = None,
    output_type: type = str,
) -> RectAgent:
    return RectAgent(config=config, llm=llm, callback=callback, output_type=output_type)
