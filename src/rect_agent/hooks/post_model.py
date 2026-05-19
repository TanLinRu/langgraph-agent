import logging
from datetime import datetime
from typing import Any

from langgraph.types import interrupt

from src.agent.context.long_term import LongTermManager
from src.agent.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

CRITICAL_TOOLS = {"execute_code", "write_file", "bash", "code_execution", "write_operation", "resource_access", "file_write", "file_read"}
_MODEL_COSTS = {"gpt-4": {"input": 0.03, "output": 0.06}, "gpt-4o": {"input": 0.01, "output": 0.03}}


def _estimate_cost(messages: list, model: str = "gpt-4o") -> float:
    rates = _MODEL_COSTS.get(model, _MODEL_COSTS["gpt-4o"])
    total = 0
    for m in messages[-3:]:
        tokens = len(str(getattr(m, "content", "") or "")) // 4
        mtype = getattr(m, "type", "")
        rate = rates.get("output", 0.03) if mtype == "ai" else rates.get("input", 0.01)
        total += tokens * rate / 1000
    return total


def _check_critical_tools(state: dict) -> list[str]:
    messages = state.get("messages", [])
    if not messages:
        return []
    last = messages[-1]
    if hasattr(last, "tool_calls"):
        tool_calls = last.tool_calls
    elif isinstance(last, dict):
        tool_calls = last.get("tool_calls")
    else:
        tool_calls = None
    if not tool_calls:
        return []
    critical = []
    for tc in tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
        if name in CRITICAL_TOOLS:
            critical.append(name)
    return critical


def build_post_model_hook(long_term: LongTermManager | None = None):
    def post_model_hook(state: dict) -> dict:
        messages = list(state.get("messages", []))

        critical = _check_critical_tools(state)
        if critical:
            result = interrupt(f"Human approval required for tools: {critical}")
            if result != "approved":
                last = messages[-1] if messages else None
                if last and (getattr(last, "tool_calls", None) or (isinstance(last, dict) and last.get("tool_calls"))):
                    tc = last.tool_calls if hasattr(last, "tool_calls") else last["tool_calls"]
                    msg = f"Tool execution rejected by user: {[t.get('name') if isinstance(t, dict) else t.name for t in tc]}"
                    return {"messages": [{"role": "tool", "tool_call_id": tc[0]["id"] if isinstance(tc[0], dict) else tc[0].id, "content": msg, "status": "rejected"}]}
                return {}
            logger.info(f"[HITL] Approved critical tools: {critical}")

        step_count = state.get("step_count", 0)
        updates = {
            "step_count": step_count + 1,
            "updated_at": datetime.now().isoformat(),
            "current_action": "",
        }

        cost = _estimate_cost(messages)
        if cost > 0:
            get_rate_limiter().add_cost(cost)
            old_usage = state.get("token_usage", {})
            updates["token_usage"] = {
                "messages": old_usage.get("messages", 0) + (len(str(getattr(messages[-1], "content", "") or "")) // 4 if messages else 0),
                "cost": old_usage.get("cost", 0) + cost,
            }

        if long_term:
            try:
                thread_id = state.get("thread_id", "")
                if thread_id:
                    long_term.save_session(thread_id, messages)
            except Exception:
                logger.warning("[PostModel] Session save failed", exc_info=True)

        return updates

    return post_model_hook
