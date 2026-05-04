"""
异步事件总线 - 用于实时推送执行状态到前端 SSE

使用方式:
    bus = get_event_bus()
    await bus.publish(ExecutionEvent(event_type="agent_status", data={...}))
    # SSE endpoint:
    async for chunk in bus.stream():
        yield chunk
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionEvent:
    """执行事件"""
    event_type: str  # 'agent_status' | 'skill_trigger' | 'task_progress' | 'step_complete'
    data: dict
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class EventBus:
    """异步发布/订阅事件总线"""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._recent_events: list[ExecutionEvent] = []
        self._max_recent = 50

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
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_recent:
            self._recent_events = self._recent_events[-self._max_recent:]

        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # 客户端太慢，丢弃事件

    def get_snapshot(self) -> dict:
        """获取当前状态快照"""
        return {
            "subscriber_count": len(self._subscribers),
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
