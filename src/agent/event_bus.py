"""
异步事件总线 - 用于实时推送执行状态到前端 SSE

事件类型:
    agent_status     - Agent 状态变更 (start/running/paused/completed/failed)
    agent_think      - LLM 调用开始
    agent_execute    - 工具执行开始
    tool_start       - 单个工具开始调用
    tool_end         - 单个工具执行完成
    tool_error       - 工具执行出错
    skill_trigger    - Skill 触发
    task_progress    - 任务进度更新
    step_complete    - 步骤完成
    compression_start - 上下文压缩开始
    compression_end  - 上下文压缩完成
    llm_call         - LLM API 调用（含耗时/成本）
    budget_warning   - Token 预算警告 (>50%)
    orchestration_step - 编排器步骤状态变更
    orchestration_complete - 编排器执行完成
    metric_update    - 指标更新
    system_health    - 系统健康状态
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncGenerator, Literal, Optional

from .trace_context import get_trace_id

logger = logging.getLogger(__name__)

EventType = Literal[
    "agent_status",
    "agent_think",
    "agent_execute",
    "tool_start",
    "tool_end",
    "tool_error",
    "skill_trigger",
    "task_progress",
    "step_complete",
    "compression_start",
    "compression_end",
    "llm_call",
    "budget_warning",
    "orchestration_step",
    "orchestration_complete",
    "metric_update",
    "system_health",
]


@dataclass
class ExecutionEvent:
    """执行事件"""
    event_type: EventType
    data: dict
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class EventBus:
    """异步发布/订阅事件总线"""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._recent_events: list[ExecutionEvent] = []
        self._max_recent = 50
        self._dropped_count: int = 0
        self._published_count: int = 0

    def subscribe(self) -> asyncio.Queue:
        """订阅事件，返回一个 Queue"""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        logger.info(f"[EventBus] New subscriber, total: {len(self._subscribers)}")
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """取消订阅"""
        self._subscribers = [s for s in self._subscribers if s is not q]
        logger.info(f"[EventBus] Subscriber removed, total: {len(self._subscribers)}")

    async def publish(self, event: ExecutionEvent):
        """发布事件到所有订阅者（非阻塞）"""
        self._published_count += 1

        if "trace_id" not in event.data:
            tid = get_trace_id()
            if tid:
                event.data["trace_id"] = tid

        self._recent_events.append(event)
        if len(self._recent_events) > self._max_recent:
            self._recent_events = self._recent_events[-self._max_recent:]

        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                self._dropped_count += 1
                logger.warning(
                    f"[EventBus] Event dropped (queue full, total dropped: {self._dropped_count}): "
                    f"type={event.event_type}, subscriber_queue_size={q.qsize()}, trace_id={event.data.get('trace_id', 'N/A')}"
                )

    def get_snapshot(self) -> dict:
        """获取当前状态快照"""
        return {
            "subscriber_count": len(self._subscribers),
            "published_count": self._published_count,
            "dropped_count": self._dropped_count,
            "recent_events": [
                {
                    "type": e.event_type,
                    "data": e.data,
                    "timestamp": e.timestamp,
                }
                for e in self._recent_events
            ],
        }

    async def stream(self) -> AsyncGenerator[str, None]:
        """SSE 格式的事件流生成器"""
        q = self.subscribe()
        try:
            while True:
                event = await q.get()
                data = json.dumps(
                    {"type": event.event_type, "data": event.data, "timestamp": event.timestamp},
                    ensure_ascii=False,
                )
                yield f"event: {event.event_type}\ndata: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(q)


# 全局单例
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局事件总线"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


async def publish_workflow_event(event_type: EventType, orchestration_id: str, data: dict):
    """发布编排器工作流事件的便捷方法"""
    tid = get_trace_id() or ""
    bus = get_event_bus()
    await bus.publish(ExecutionEvent(
        event_type=event_type,
        data={"trace_id": tid, "orchestration_id": orchestration_id, **data},
    ))
