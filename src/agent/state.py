from typing import TypedDict, Annotated, Literal, Optional
import operator
from datetime import datetime
from dataclasses import dataclass, field

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


# ========== Dynamic Orchestrator State ==========

@dataclass
class OrchestratorStep:
    """编排器单个步骤的状态"""
    step_id: str              # e.g. "step-1"
    agent_id: str             # "builtin-code_review" or "skill:debugging"
    agent_name: str           # "Code Review Agent"
    description: str          # what this step does
    depends_on: list[str] = field(default_factory=list)  # step_ids this depends on
    status: str = "pending"   # pending|running|completed|failed|skipped
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: int = 0


@dataclass
class OrchestratorState:
    """编排器整体状态"""
    orchestration_id: str
    thread_id: str
    input_text: str
    plan_summary: str = ""
    steps: list[OrchestratorStep] = field(default_factory=list)
    status: str = "planning"  # planning|running|completed|failed|rolled_back
    current_step_id: Optional[str] = None
    final_output: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    replan_count: int = 0