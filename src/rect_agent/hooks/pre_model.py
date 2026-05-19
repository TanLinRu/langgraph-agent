import logging
from typing import Any

from langchain_core.messages import RemoveMessage

from src.agent.rate_limiter import get_rate_limiter, get_tool_breakers
from src.agent.context.long_term import LongTermManager
from src.agent.context.compression import ContextCompressor
from src.agent.schemas.agent_protocol import ERROR_CODES, StructuredAgentError, ErrorLevel

logger = logging.getLogger(__name__)


def build_pre_model_hook(
    long_term: LongTermManager | None = None,
    compressor: ContextCompressor | None = None,
):
    def pre_model_hook(state: dict) -> dict:
        rate_limiter = get_rate_limiter()
        if not rate_limiter.check_limit():
            raise StructuredAgentError(
                error_code="LLM_RATE_LIMIT",
                error_type="RECOVERABLE",
                message="请求频率超限",
                retryable=True,
                error_level=ErrorLevel.HIGH,
                trace_id=state.get("trace_id", ""),
            )

        llm_breaker = get_tool_breakers().get_breaker("_llm")
        if not llm_breaker.can_execute():
            raise StructuredAgentError(
                error_code="LLM_CIRCUIT_OPEN",
                error_type="RECOVERABLE",
                message="LLM 熔断器开启",
                retryable=True,
                error_level=ErrorLevel.HIGH,
                trace_id=state.get("trace_id", ""),
            )

        token_usage = state.get("token_usage", {})
        percentage = token_usage.get("percentage", 0)
        compression_count = state.get("compression_count", 0)

        if percentage >= 70 and compressor and compression_count < 5:
            try:
                messages = list(state.get("messages", []))
                result = compressor.compress(context={"messages": messages})
                if result and result.summary_message:
                    removed = [
                        RemoveMessage(id=m.id)
                        for m in messages
                        if getattr(m, "id", None) and hasattr(result.summary_message, "id") and m.id != result.summary_message.id
                    ]
                    updates = {"messages": [result.summary_message], "compression_count": compression_count + 1}
                    if removed:
                        updates["messages"].extend(removed)
                    return updates
            except Exception:
                logger.warning("[PreModel] Compression failed", exc_info=True)

        if long_term:
            try:
                thread_id = state.get("thread_id", "")
                user_id = state.get("user_id", "")
                if thread_id and user_id:
                    memories = long_term.search_similar(user_id, thread_id, top_k=3)
                    if memories:
                        return {"injected_memory": list(memories)}
            except Exception:
                logger.warning("[PreModel] Memory retrieval failed", exc_info=True)

        return {}

    return pre_model_hook
