from typing import TypedDict, Annotated, Literal, Optional
import operator
from datetime import datetime

from langgraph.graph import MessagesState


class AgentState(TypedDict):
    """Agent 状态定义"""
    messages: Annotated[list, operator.add]
    thread_id: str
    task_status: Literal["pending", "in_progress", "completed", "failed"]
    current_plan: list | None
    compression_count: int
    checkpoint: str | None
    created_at: str
    updated_at: str
    sop_name: str | None
    sop_step: int | None


def create_initial_state(thread_id: str = "default") -> AgentState:
    """创建初始状态"""
    now = datetime.now().isoformat()
    return {
        "messages": [],
        "thread_id": thread_id,
        "task_status": "pending",
        "current_plan": None,
        "compression_count": 0,
        "checkpoint": None,
        "created_at": now,
        "updated_at": now,
        "sop_name": None,
        "sop_step": None,
    }


class SubAgentState(MessagesState):
    """Sub-agent 共享状态，用于 supervisor 模式下的多代理协作。"""
    task_description: Optional[str] = None