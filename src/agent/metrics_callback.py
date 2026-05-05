import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from .event_bus import get_event_bus, ExecutionEvent
from .metrics_collector import get_metrics_collector
from .cost_calculator import estimate_cost, normalize_model_name

logger = logging.getLogger(__name__)


class MetricsCallbackHandler(BaseCallbackHandler):
    def __init__(self, execution_id: str = ""):
        super().__init__()
        self.execution_id = execution_id
        self._bus = get_event_bus()
        self._collector = get_metrics_collector()
        self._active_spans: dict[str, str] = {}
        self._current_model = "gpt-4o"

    def _publish(self, event_type: str, data: dict):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._bus.publish(ExecutionEvent(
                event_type=event_type,
                data={**data, "execution_id": self.execution_id},
            )))
        except RuntimeError:
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._bus.publish(ExecutionEvent(
                    event_type=event_type,
                    data={**data, "execution_id": self.execution_id},
                )))
                loop.close()
            except Exception as e:
                logger.warning(f"[MetricsCallback] Failed to publish: {e}")

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
        model = serialized.get("name", "gpt-4o")
        self._current_model = model
        span_id = self._collector.start_span(
            "llm_call",
            execution_id=self.execution_id,
            model=model,
        )
        self._active_spans[str(run_id)] = span_id
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
        span_id = self._active_spans.pop(str(run_id), None)
        if not span_id:
            return

        usage = {}
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        cost = estimate_cost(self._current_model, prompt_tokens, completion_tokens)

        self._collector.end_span(
            span_id,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            model=self._current_model,
        )

        self._publish("metric_update", {
            "metric_name": "llm_call",
            "total_tokens": total_tokens,
            "cost_usd": cost,
            "model": self._current_model,
        })

        self._publish("task_progress", {
            "stage": "llm_complete",
            "tokens": total_tokens,
            "run_id": str(run_id),
        })

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> Any:
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self._collector.end_span(span_id, status="error", error=str(error))

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
        span_id = self._collector.start_span(
            "tool_call",
            execution_id=self.execution_id,
            tool_name=tool_name,
        )
        self._active_spans[str(run_id)] = span_id
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
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self._collector.end_span(span_id, status="ok")

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self._collector.end_span(span_id, status="error", error=str(error))


__all__ = ["MetricsCallbackHandler"]