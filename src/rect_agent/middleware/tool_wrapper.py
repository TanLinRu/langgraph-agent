import time
import logging
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.agent.rate_limiter import get_tool_breakers
from src.agent.retry_handler import ToolRetryConfig
from src.agent.schemas.agent_protocol import ERROR_CODES, StructuredAgentError

logger = logging.getLogger(__name__)

_idempotency_cache: dict[str, str] = {}


def _check_idempotency(tool_call: dict) -> str | None:
    args = tool_call.get("args", tool_call.get("arguments", {}))
    key = args.get("idempotency_key", "")
    if not key:
        return None
    return _idempotency_cache.get(key)


def _record_idempotency(tool_call: dict, content: str):
    args = tool_call.get("args", tool_call.get("arguments", {}))
    key = args.get("idempotency_key", "")
    if key:
        _idempotency_cache[key] = content


def production_tool_wrapper(request: ToolCallRequest, execute: Any) -> ToolMessage:
    tc = request.tool_call
    tool_name = tc.get("name", "unknown")
    tool_call_id = tc.get("id", "") or ""
    start_time = time.time()

    cached = _check_idempotency(tc)
    if cached:
        logger.info(f"[ToolWrapper] Cache hit for {tool_name}")
        return ToolMessage(content=cached, tool_call_id=tool_call_id, status="success")

    if not get_tool_breakers().can_execute(tool_name):
        logger.warning(f"[ToolWrapper] Breaker open for {tool_name}")
        return ToolMessage(
            content=f"熔断器已开启，跳过 {tool_name}",
            tool_call_id=tool_call_id,
            status="error",
        )

    max_retries = ToolRetryConfig.max_retries
    delay = ToolRetryConfig.initial_delay

    for attempt in range(max_retries + 1):
        try:
            result = execute(request)
            elapsed = time.time() - start_time
            content = str(result.content) if hasattr(result, "content") else str(result)
            get_tool_breakers().record_success(tool_name)
            _record_idempotency(request.tool_call, content)
            logger.info(f"[ToolWrapper] {tool_name} succeeded in {elapsed:.2f}s (attempt {attempt + 1})")
            return ToolMessage(content=content, tool_call_id=tool_call_id, status="success")
        except StructuredAgentError as e:
            if not e.envelope.retryable:
                raise
            if attempt >= max_retries:
                get_tool_breakers().record_failure(tool_name)
                raise
            delay *= ToolRetryConfig.backoff_factor
            logger.warning(f"[ToolWrapper] {tool_name} attempt {attempt + 1} failed, retrying in {delay:.1f}s")
            time.sleep(delay)
        except Exception as e:
            error_info = ERROR_CODES.get("TOOL_EXEC_ERROR", {})
            if error_info.get("retryable", False) and attempt < max_retries:
                delay *= ToolRetryConfig.backoff_factor
                time.sleep(delay)
                continue
            get_tool_breakers().record_failure(tool_name)
            raise StructuredAgentError(
                error_code="TOOL_EXEC_ERROR",
                error_type="FATAL",
                message=f"{tool_name} failed: {e}",
                retryable=False,
                error_level="HIGH",
                trace_id="",
            )

    return ToolMessage(content="工具执行失败", tool_call_id=tool_call_id, status="error")
