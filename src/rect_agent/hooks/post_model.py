import logging
from datetime import datetime
from typing import Any

from langgraph.types import interrupt

from src.agent.audit_logger import log_error as audit_log_error
from src.agent.context.long_term import LongTermManager
from src.agent.rate_limiter import get_rate_limiter
from src.rect_agent.shared import CRITICAL_TOOLS, check_critical_tools as _check_critical_tools

logger = logging.getLogger(__name__)

_MODEL_COSTS = {"gpt-4": {"input": 0.03, "output": 0.06}, "gpt-4o": {"input": 0.01, "output": 0.03}}

FINAL_ANSWER_MARKERS = {
    "zh": ["最终答案", "综上所述", "总结"],
    "en": ["final answer", "in summary", "to summarize"],
}


def _detect_final_answer(messages: list) -> bool:
    if not messages:
        return False
    last = messages[-1]
    content = getattr(last, "content", "") or (last.get("content", "") if isinstance(last, dict) else "")
    if not content:
        return False
    lower = content.lower()
    for markers in FINAL_ANSWER_MARKERS.values():
        for marker in markers:
            if marker.lower() in lower:
                return True
    return False


def _detect_homogeneous_tool_calls(messages: list) -> bool:
    recent = []
    for m in reversed(messages[-10:]):
        tcs = getattr(m, "tool_calls", None)
        if not tcs and isinstance(m, dict):
            tcs = m.get("tool_calls")
        if tcs:
            for tc in tcs:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                recent.append((name, str(args)))
    if len(recent) >= 3:
        last3 = recent[-3:]
        return len(set(t[0] for t in last3)) == 1 and len(set(t[1] for t in last3)) == 1
    return False


def _estimate_cost(messages: list, model: str = "gpt-4o") -> float:
    rates = _MODEL_COSTS.get(model, _MODEL_COSTS["gpt-4o"])
    total = 0
    for m in messages[-3:]:
        tokens = len(str(getattr(m, "content", "") or "")) // 4
        mtype = getattr(m, "type", "")
        rate = rates.get("output", 0.03) if mtype == "ai" else rates.get("input", 0.01)
        total += tokens * rate / 1000
    return total


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

        if _detect_final_answer(messages):
            updates["task_status"] = "completed"
            updates["current_action"] = "early_stop:final_answer"
            logger.info("[PostModel] Early stop triggered by Final Answer")

        if _detect_homogeneous_tool_calls(messages):
            updates["task_status"] = "completed"
            updates["current_action"] = "early_stop:homogeneous_loop"
            logger.info("[PostModel] Early stop triggered by homogeneous tool calls")

        if state.get("step_count", 0) >= 25:
            updates["task_status"] = "completed"
            updates["current_action"] = "early_stop:max_steps"
            logger.info("[PostModel] Early stop triggered by max steps")

        cost = _estimate_cost(messages)
        if cost > 0:
            get_rate_limiter().add_cost(cost)
            old_usage = state.get("token_usage", {})
            updates["token_usage"] = {
                "messages": old_usage.get("messages", 0) + (len(str(getattr(messages[-1], "content", "") or "")) // 4 if messages else 0),
                "cost": old_usage.get("cost", 0) + cost,
            }

        try:
            tool_names = []
            if messages:
                last = messages[-1]
                tcs = getattr(last, "tool_calls", None)
                if tcs:
                    tool_names = [t.get("name") for t in (tcs if isinstance(tcs, list) else [])]
            audit_log_error(
                error={"error_code": "LLM_CALL", "error_type": "RECOVERABLE", "retryable": False},
                trace_id=state.get("trace_id", ""),
                thread_id=state.get("thread_id", ""),
                context={"step": step_count + 1, "tool_calls": tool_names, "status": "completed"},
            )
        except Exception:
            logger.warning("[PostModel] Audit log failed", exc_info=True)

        if long_term:
            try:
                thread_id = state.get("thread_id", "")
                if thread_id:
                    long_term.save_session(thread_id, messages)
            except Exception:
                logger.warning("[PostModel] Session save failed", exc_info=True)

        return updates

    return post_model_hook
