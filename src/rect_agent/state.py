from typing import TypedDict, Annotated, Literal
from datetime import datetime

from langgraph.graph.message import add_messages

from src.agent.state import token_budget_reducer, ToolResultSummary


class RectAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    remaining_steps: int
    thread_id: str
    user_id: str
    task_status: Literal["pending", "in_progress", "completed", "failed", "paused", "aborted"]
    current_plan: list | None
    compression_count: int
    checkpoint: str | None
    created_at: str
    updated_at: str
    sop_name: str | None
    sop_step: int | None
    token_usage: Annotated[dict, token_budget_reducer]
    hot_tool_results: list[ToolResultSummary]
    injected_memory: list
    step_count: int
    current_action: str
    last_error: dict | None
    trace_id: str


def create_initial_state(thread_id: str = "default") -> RectAgentState:
    now = datetime.now().isoformat()
    return {
        "messages": [],
        "remaining_steps": 50,
        "thread_id": thread_id,
        "user_id": "default",
        "task_status": "pending",
        "current_plan": None,
        "compression_count": 0,
        "checkpoint": None,
        "created_at": now,
        "updated_at": now,
        "sop_name": None,
        "sop_step": None,
        "token_usage": {
            "messages": 0,
            "hot_zone": 0,
            "budget": 128000,
            "percentage": 0.0,
        },
        "hot_tool_results": [],
        "injected_memory": [],
        "step_count": 0,
        "current_action": "",
        "last_error": None,
        "trace_id": "",
    }
