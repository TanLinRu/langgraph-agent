"""共享常量和工具函数，避免 hooks/ 和 middleware/ 之间的循环导入。"""

CRITICAL_TOOLS = {
    "execute_code", "write_file", "bash", "code_execution",
    "write_operation", "resource_access", "file_write", "file_read",
}


def check_critical_tools(state: dict) -> list[str]:
    messages = state.get("messages", [])
    if not messages:
        return []
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or (last.get("tool_calls") if isinstance(last, dict) else None)
    if not tool_calls:
        return []
    return [
        tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
        for tc in tool_calls
        if (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")) in CRITICAL_TOOLS
    ]
