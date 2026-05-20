import time
import logging
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.rect_agent.middleware.context import RectContext
from src.rect_agent.middleware.tool_wrapper import _check_idempotency, _record_idempotency, _check_budget
from src.rect_agent.shared import CRITICAL_TOOLS
from src.agent.retry_handler import ToolRetryConfig
from src.agent.schemas.agent_protocol import StructuredAgentError
from src.agent.human_in_loop import ApprovalType, request_approval
from src.agent.rate_limiter import get_tool_breakers

logger = logging.getLogger(__name__)


@dataclass
class RectTool:
    function: Callable
    name: str
    description: str
    parameters_schema: type[BaseModel] | None = None
    max_retries: int = ToolRetryConfig.max_retries
    requires_approval: bool = False
    timeout: float = 30.0

    def execute(self, request: ToolCallRequest, ctx: RectContext | None = None) -> ToolMessage:
        tc = request.tool_call
        tool_call_id = tc.get("id", "") or ""
        tool_name = self.name

        cached = _check_idempotency(tc)
        if cached:
            return ToolMessage(content=cached, tool_call_id=tool_call_id, status="success")

        tool_breakers = ctx.tool_breakers if ctx else get_tool_breakers()
        if not tool_breakers.can_execute(tool_name):
            return ToolMessage(content=f"断路器已开启，跳过 {tool_name}", tool_call_id=tool_call_id, status="error")

        if not _check_budget(0.01, tool_name):
            return ToolMessage(content="预算不足，跳过", tool_call_id=tool_call_id, status="error")

        if self.requires_approval:
            try:
                result = request_approval(ApprovalType.CODE_EXECUTION, tool_name)
                if not result.approved:
                    return ToolMessage(content=f"工具 {tool_name} 被拒绝", tool_call_id=tool_call_id, status="rejected")
            except Exception:
                return ToolMessage(content="审批排队", tool_call_id=tool_call_id, status="pending")

        delay = ToolRetryConfig.initial_delay
        for attempt in range(self.max_retries + 1):
            try:
                result = self.function(request)
                content = str(result.content) if hasattr(result, "content") else str(result)
                tool_breakers.record_success(tool_name)
                _record_idempotency(tc, content)
                return ToolMessage(content=content, tool_call_id=tool_call_id, status="success")
            except StructuredAgentError as e:
                if not e.envelope.retryable or attempt >= self.max_retries:
                    tool_breakers.record_failure(tool_name)
                    raise
                time.sleep(delay)
                delay *= ToolRetryConfig.backoff_factor
            except Exception:
                if attempt >= self.max_retries:
                    tool_breakers.record_failure(tool_name)
                    break
                time.sleep(delay)
                delay *= ToolRetryConfig.backoff_factor

        return ToolMessage(content="工具执行失败", tool_call_id=tool_call_id, status="error")
