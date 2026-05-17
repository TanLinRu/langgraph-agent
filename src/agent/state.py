from typing import TypedDict, Annotated, Literal, Optional, Any
import operator
from datetime import datetime
from dataclasses import dataclass, field

from langgraph.graph import MessagesState


@dataclass
class ToolResultSummary(TypedDict):
    """Tool Result Hot Zone 摘要 (设计参考: context_design.md 4.1)"""
    tool_call_id: str
    tool_name: str
    summary: str
    status: str  # success / failed
    timestamp: str
    access_count: int = 0
    full_content: str = ""  # 热区条目保留完整原文
    is_hot: bool = False     # 是否在热区中


MODEL_FORMATTING_OVERHEAD = {
    "gpt-4": 4,
    "gpt-4o": 4,
    "gpt-4o-mini": 4,
    "gpt-3.5-turbo": 4,
}


def token_budget_reducer(existing: dict, new: dict) -> dict:
    """Token 预算累加 + 百分比计算

    模型格式化 overhead（每条消息加 4 tokens，用于 role/content/timestamp 格式）
    """
    result = dict(existing)
    model = result.get("model", "gpt-4o")
    overhead = MODEL_FORMATTING_OVERHEAD.get(model, 4)

    for key, value in new.items():
        if key in ['model', 'budget']:
            result[key] = value
        else:
            result[key] = result.get(key, 0) + value

    msg_tokens = result.get("messages", 0)
    overhead_tokens = result.get("message_count", 0) * overhead
    total_with_overhead = msg_tokens + overhead_tokens

    budget = result.get("budget", 128000)
    result["percentage"] = round(total_with_overhead / max(budget, 1) * 100, 1)
    result["total_with_overhead"] = total_with_overhead
    result["overhead_tokens"] = overhead_tokens
    return result


def smart_message_reducer(existing: list, new: list) -> list:
    """智能消息合并：超过 MAX_MESSAGES 时通知压缩

    设计参考: context_design.md 3.3 节
    注意：实际压缩由 compress 节点执行，这里只记录状态
    """
    MAX_MESSAGES = 20
    combined = existing + new
    if len(combined) <= MAX_MESSAGES:
        return combined
    return combined


class AgentState(TypedDict):
    """Agent 状态定义"""
    messages: Annotated[list, smart_message_reducer]
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


def create_initial_state(thread_id: str = "default") -> AgentState:
    """创建初始状态"""
    now = datetime.now().isoformat()
    return {
        "messages": [],
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