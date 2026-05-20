import time
import logging
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.agent.rate_limiter import get_rate_limiter, get_tool_breakers
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


def _get_long_term(ctx: Any = None):
    if ctx and ctx.long_term:
        return ctx.long_term
    from src.agent.context.long_term import LongTermManager, LongTermConfig
    return LongTermManager(LongTermConfig())


def _check_budget(estimated_cost: float, tool_name: str) -> bool:
    limiter = get_rate_limiter()
    ok, msg = limiter.check_cost_limit()
    if not ok:
        logger.warning(f"[ToolWrapper] Budget exceeded for {tool_name}: {msg}")
    return ok


def production_tool_wrapper(
    request: ToolCallRequest,
    execute: Any,
    ctx: Any = None,
) -> ToolMessage:
    tc = request.tool_call
    tool_name = tc.get("name", "unknown")
    tool_call_id = tc.get("id", "") or ""
    start_time = time.time()

    state = getattr(request, "state", None) or {}
    trace_id = state.get("trace_id", "") or (tc.get("args", {}) or {}).get("__trace_id", "") or ""

    rate_limiter = ctx.rate_limiter if ctx else get_rate_limiter()
    tool_breakers = ctx.tool_breakers if ctx else get_tool_breakers()

    cached = _check_idempotency(tc)
    if cached:
        logger.info(f"[ToolWrapper] Cache hit for {tool_name}")
        return ToolMessage(content=cached, tool_call_id=tool_call_id, status="success")

    thread_id = state.get("thread_id", "") or (tc.get("args", {}) or {}).get("__thread_id", "") or ""
    if thread_id:
        try:
            mgr = _get_long_term(ctx)
            persisted = mgr.load_tool_result(thread_id, tool_call_id)
            if persisted:
                content = persisted.get("content", "")
                _idempotency_cache[tool_call_id] = content
                logger.info(f"[ToolWrapper] SQLite cache hit for {tool_name}")
                return ToolMessage(content=content, tool_call_id=tool_call_id, status="success")
        except Exception:
            logger.warning(f"[ToolWrapper] SQLite lookup failed for {tool_name}", exc_info=True)

    if not tool_breakers.can_execute(tool_name):
        logger.warning(f"[ToolWrapper] Breaker open for {tool_name}")
        return ToolMessage(
            content=f"熔断器已开启，跳过 {tool_name}",
            tool_call_id=tool_call_id,
            status="error",
        )

    max_retries = ToolRetryConfig.max_retries
    delay = ToolRetryConfig.initial_delay

    if not _check_budget(delay * 0.01, tool_name):
        return ToolMessage(content="预算不足，跳过重试", tool_call_id=tool_call_id, status="error")

    for attempt in range(max_retries + 1):
        try:
            result = execute(request)
            elapsed = time.time() - start_time
            content = str(result.content) if hasattr(result, "content") else str(result)
            tool_breakers.record_success(tool_name)
            _record_idempotency(request.tool_call, content)
            if thread_id:
                try:
                    _get_long_term(ctx).save_tool_results(thread_id, [{"tool_call_id": tool_call_id, "tool_name": tool_name, "content": content}])
                except Exception:
                    logger.warning(f"[ToolWrapper] SQLite save failed for {tool_name}", exc_info=True)
            logger.info(f"[ToolWrapper] {tool_name} succeeded in {elapsed:.2f}s (attempt {attempt + 1})")
            return ToolMessage(content=content, tool_call_id=tool_call_id, status="success")
        except StructuredAgentError as e:
            if not e.envelope.retryable:
                raise
            if attempt >= max_retries:
                tool_breakers.record_failure(tool_name)
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
            tool_breakers.record_failure(tool_name)
            raise StructuredAgentError(
                error_code="TOOL_EXEC_ERROR",
                error_type="FATAL",
                message=f"{tool_name} failed: {e}",
                retryable=False,
                error_level="HIGH",
                trace_id=trace_id,
            )

    return ToolMessage(content="工具执行失败", tool_call_id=tool_call_id, status="error")
