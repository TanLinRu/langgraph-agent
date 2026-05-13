"""
LangGraph Callback Handler -> EventBus 桥接

将 LangGraph 的生命周期事件映射为 EventBus 的 ExecutionEvent，
用于实时 SSE 推送到前端。
"""
import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from .event_bus import get_event_bus, ExecutionEvent
from .trace_context import get_trace_id

logger = logging.getLogger(__name__)


class EventBusCallbackHandler(BaseCallbackHandler):
    """将 LangGraph 回调事件转发到 EventBus。"""

    def __init__(self, execution_id: str = ""):
        super().__init__()
        self.execution_id = execution_id
        self._bus = get_event_bus()

    def _publish(self, event_type: str, data: dict):
        """同步发布事件（在事件循环中调度异步 publish）。"""
        tid = get_trace_id() or self.execution_id
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._bus.publish(ExecutionEvent(
                event_type=event_type,
                data={**data, "trace_id": tid},
            )))
        except RuntimeError:
            # 没有运行的事件循环，用新循环
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._bus.publish(ExecutionEvent(
                    event_type=event_type,
                    data={**data, "trace_id": tid},
                )))
                loop.close()
            except Exception as e:
                logger.warning(f"[EventBusCallback] Failed to publish: {e}")

    # === Chain events (sub-agent 调用) ===

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        chain_name = serialized.get("name", "unknown")
        # 过滤掉 supervisor 内部的 chain 事件，只关注 sub-agent
        if chain_name and chain_name not in ("LangGraph", "RunnableSequence"):
            self._publish("agent_status", {
                "agent_id": chain_name,
                "agent_name": chain_name,
                "status": "running",
            })

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._publish("step_complete", {
            "status": "completed",
            "run_id": str(run_id),
        })

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._publish("agent_status", {
            "status": "failed",
            "error": str(error),
            "run_id": str(run_id),
        })

    # === Tool events ===

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        inputs: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        tool_name = serialized.get("name", "unknown")
        self._publish("skill_trigger", {
            "tool_name": tool_name,
            "input": input_str[:200] if input_str else "",
        })

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        pass  # tool 完成事件已通过 step_complete 覆盖

    # === LLM events ===

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        self._publish("task_progress", {
            "stage": "llm_call",
            "run_id": str(run_id),
        })

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> Any:
        # 提取 token 使用信息
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            if usage:
                self._publish("task_progress", {
                    "stage": "llm_complete",
                    "tokens": usage.get("total_tokens", 0),
                    "run_id": str(run_id),
                })
