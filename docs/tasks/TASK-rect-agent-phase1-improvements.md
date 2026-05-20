# TASK-rect-agent-phase1-improvements.md (v2 — 审查后修正版)

> rect-agent 三阶段改进计划 — 12 步骤，覆盖检查点/LLM重试/结构化输出/trace_id/降级/审计/预算/DI/RectTool/MemoryManager/幂等/早停
>
> **审查说明**: 本文档已通过架构审查（2026-05-20），标注 ✅ 为审查通过步骤，⚠️ 为需修正步骤，❌ 为未通过步骤。所有 ⚠️ 已附带修正方案。

---

## 任务目标

在不动原有 `src/agent/` 的前提下，补齐 `src/rect_agent/` 的生产能力缺口，全部复用 LangChain/LangGraph 内置 API 和现有的可靠性基础设施。

## 当前状态

| # | 缺口 | 当前行为 | 影响 |
|---|------|---------|------|
| 1 | graph.py 无检查点 | Studio 模式会话不持久化 | 每次重启丢失上下文 |
| 2 | LLM 无重试 | API 抖动直接导致请求失败 | 生产高概率失败 |
| 3 | 无输出类型强制 | invoke 返回原始 dict | 调用方需手动解析 |
| 4 | trace_id 硬编码空串 | 工具异常无追踪 id | 链路追踪断裂 |
| 5 | 无优雅降级 | LLM 不可用时直接抛异常 | 无降级响应 |
| 6 | 无审计日志 | 无本地调用记录 | 无法事后追溯 |
| 7 | 无重试前预算校验 | 可能耗尽预算还重试 | 成本失控 |
| 8 | 无依赖注入封装 | 全局变量散落各处 | 测试困难 |
| 9 | 工具包装散乱 | 函数式包装 vs dataclass | 维护成本高 |
| 10 | 无 MemoryManager 外观 | L1-L4 分散调用 | 耦合 context/ 模块 |
| 11 | 无 SQLite 幂等持久化 | 仅内存缓存 | 跨会话不隔离 |
| 12 | 无早停检测 | 直到超步或超压缩才停 | 浪费 token |

---

## 全阶段总览

| 阶段 | 步骤范围 | 文件数 | 总行数 | 推荐顺序 |
|------|---------|--------|--------|---------|
| **Phase 1** | Step 1-4: 检查点/LLM重试/output_type/trace_id | 4 文件 | ~28 行 | **先做** |
| **Phase 2** | Step 8→5→6→7: RectContext/降级/审计/预算 | 5 文件 | ~50 行 | 2 |
| **Phase 3** | Step 11→12→9→10: SQLite幂等/早停/RectTool/MemoryManager | 5 文件 | ~135 行 | 3 |

**阶段间依赖**: Phase 2 中 Step 8 (RectContext) 应**先于** Step 5/6/7 实施，因为三者都可消费 RectContext。Phase 3 中 Step 11 (SQLite幂等) 可在 RectContext 就绪后复用其 `long_term` 实例。

---

## Phase 1 — 高影响，低工作量

---

### Step 1: graph.py — 检查点 ⚠️ 需修正

**方法**: `SqliteSaver.from_conn_string()` 返回的是 context manager，不是 `SqliteSaver` 实例。需用直接构造器。

**文件**: `src/rect_agent/graph.py`

**改动**:
1. 新增导入:
```python
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
```
2. `create_react_agent` 调用新增:
```python
checkpointer=SqliteSaver(
    sqlite3.connect("memory/rect_sessions.db", check_same_thread=False)
),
```

**验证**: `python -c "from src.rect_agent.graph import graph; print(graph.checkpointer is not None)"` → `True`

**修正说明**: `SqliteSaver.from_conn_string()` 返回 `contextlib._GeneratorContextManager`，不能直接传给 `create_react_agent(checkpointer=...)`。`check_same_thread=False` 是必须的（LangGraph 可能从不同线程调用检查点）。

---

### Step 2: agent.py — LLM 重试 (with_retry + breaker 联动) ⚠️ 需修正

**方法**: `RunnableLambda(breaker_check) | llm.with_retry()`。`create_react_agent` 的 `model` 参数接受 `Runnable`。

**文件**: `src/rect_agent/agent.py`

**⚠️ 关键陷阱**: `with_retry()` 默认 `retry_if_exception_type=(Exception,)`，而 `StructuredAgentError` 是 `Exception` 子类。breaker open 抛出的 `StructuredAgentError` **会被 with_retry 捕获并重试 3 次**，完全违背"不重试"的意图。必须自定义 `retry_if_exception_type`。

**⚠️ Mock 兼容性**: 测试传 `llm=MagicMock()` — `MagicMock` 没有 `with_retry()`。需 fallback。

**改动**:
1. 新增导入:
```python
from langchain_core.runnables import RunnableLambda
from src.agent.schemas.agent_protocol import StructuredAgentError, ErrorLevel
```
2. 在 `__init__` 之前新增:
```python
def _build_llm_with_breaker(self):
    def breaker_check(input):
        if not get_tool_breakers().get_breaker("_llm").can_execute():
            raise StructuredAgentError(
                error_code="LLM_CIRCUIT_OPEN", error_type="RECOVERABLE",
                message="LLM 熔断器开启", retryable=False,
                error_level=ErrorLevel.HIGH,
            )
        return input
    return RunnableLambda(breaker_check) | self.llm.with_retry(
        stop_after_attempt=4,
        retry_if_exception_type=(TimeoutError, ConnectionError),
    )
```
3. `_build_graph` 中替换: `model=self.llm` → `model=self._build_llm_with_breaker()`，但加 fallback:
```python
model = self._build_llm_with_breaker() if hasattr(self.llm, "with_retry") else self.llm
```

**逻辑**:
```
llm_input → breaker can_execute? → NO → 抛 StructuredAgentError (不重试, 立即失败)
                                 → YES → llm 调用 (with_retry ×4, 仅重试 TimeoutError/ConnectionError)
```

**验证**:
- `python -m pytest tests/test_rect_agent.py -v -k "agent" --tb=short` → All passed
- 新增测试: mock `can_execute()` return False → 确认 `StructuredAgentError` 直接抛出，无重试

---

### Step 3: agent.py + __init__.py — output_type 泛型 ⚠️ 需修正

**方法**: `Generic[OutputT]` + `invoke` 出口 `model_validate`

**文件**: `src/rect_agent/agent.py`, `src/rect_agent/__init__.py`

**⚠️ 问题**: 当 `output_type=str` 时调用 `str.model_validate_json()` — 不存在。需要分支处理。

**agent.py 改动**:
1. 新增导入:
```python
from typing import Generic, TypeVar
from pydantic import BaseModel
```
2. 新增变量: `OutputT = TypeVar("OutputT", bound=BaseModel | str)`
3. 类签名: `class RectAgent(Generic[OutputT]):`
4. `__init__` 新增参数 `output_type: type[OutputT] = str`
5. `invoke` 方法:
```python
def invoke(self, input_data: dict, config: dict | None = None) -> OutputT:
    if self._graph is None:
        self.compile()
    result = self._graph.invoke(input_data, config or {})
    messages = result.get("messages", [])
    if not messages:
        return result  # type: ignore
    last = messages[-1]
    content = getattr(last, "content", "") or ""
    if self._output_schema is str:
        return content  # type: ignore
    return self._output_schema.model_validate_json(content)
```

**__init__.py 改动**:
1. 新增导出 `OutputT`:
```python
from .agent import RectAgent, create_rect_agent, OutputT
```

**设计决策**:
- `model_validate_json` 接收 LLM 返回的 JSON 字符串
- 只校验最后一条 AI 消息，不校验历史
- 不侵入 `create_react_agent` 内部（它不支持 output_type 参数）
- 运行时验证由 `model_validate_json` 保证，Mypy 静态验证由 `Generic[OutputT]` 保证

**验证**: `python -c "from src.rect_agent import RectAgent; a = RectAgent(llm=None, output_type=str); print(type(a).__name__)"` → `RectAgent`

---

### Step 4: middleware/tool_wrapper.py — trace_id 透传 ✅ 通过

**方法**: 从 `request.state` 或 `tool_call.args` 取 trace_id

**文件**: `src/rect_agent/middleware/tool_wrapper.py`

**改动**:
1. 第 36 行后新增:
```python
state = getattr(request, "state", None) or {}
trace_id = state.get("trace_id", "") or (tc.get("args", {}) or {}).get("__trace_id", "") or ""
```
2. 第 79-86 行 `StructuredAgentError` 构造使用提取的 `trace_id`:
```python
raise StructuredAgentError(
    ...
    trace_id=trace_id,  # 修复
)
```

**优先级顺序**: `request.state.trace_id` → `tool_call.args.__trace_id` → `""`

**验证**: 手动构造 `ToolCallRequest` 并设 `state={"trace_id":"t1"}` → 异常中 `error.trace_id == "t1"`

---

## Phase 2 — 高影响，中工作量

**执行顺序说明**: 先做 Step 8 (RectContext) 再做 5/6/7，因为三者都可消费 RectContext 获得配置的依赖实例。

---

### Step 8: RectContext 轻量注入 ✅ 通过

**文件**: `src/rect_agent/middleware/context.py` (新文件), `src/rect_agent/tools/wrapper.py`

**方法**: dataclass 封装依赖，通过 `build_tool_node()` 闭包注入。

**新文件 `middleware/context.py`**:
```python
from dataclasses import dataclass, field
from src.agent.rate_limiter import RateLimiter, ToolCircuitBreaker, get_rate_limiter, get_tool_breakers
from src.agent.config import AgentConfig


@dataclass
class RectContext:
    """有限范围的依赖上下文，不替代 LangGraph State。
    
    所有字段都有默认工厂，无参构造时全部使用全局函数。
    """
    rate_limiter: RateLimiter = field(default_factory=get_rate_limiter)
    tool_breakers: ToolCircuitBreaker = field(default_factory=get_tool_breakers)
    config: AgentConfig | None = None
    long_term: "LongTermManager | None" = None
```

**tools/wrapper.py 改动**:
1. 新增导入 `from src.rect_agent.middleware.context import RectContext`
2. `build_tool_node()` 新增 `ctx: RectContext | None = None` 参数
3. `production_tool_wrapper` 改为闭包捕获 `ctx`:
```python
def build_tool_node(ctx: RectContext | None = None) -> ToolNode:
    def _wrapper(request, execute):
        return production_tool_wrapper(request, execute, ctx=ctx)
    return ToolNode(TOOLS, handle_tool_errors=False, wrap_tool_call=_wrapper)
```
4. `production_tool_wrapper` 签名新增 `ctx: RectContext | None = None`:
```python
def production_tool_wrapper(request, execute, ctx=None):
    rate_limiter = ctx.rate_limiter if ctx else get_rate_limiter()
    tool_breakers = ctx.tool_breakers if ctx else get_tool_breakers()
    # 使用 rate_limiter / tool_breakers 替代全局函数调用
```

**验证**: `build_tool_node()` 无参调用 → 内部 `ctx is None` → fallback 全局函数，行为不变

---

### Step 5: 优雅降级集成 ⚠️ 需修正

**⚠️ 问题**: `ServiceHealthChecker()` 构造器**不接受参数** — `failure_threshold` 是硬编码的。

**文件**: `src/rect_agent/agent.py`, `src/rect_agent/hooks/pre_model.py`

**agent.py 改动**:
1. 新增导入 `from src.agent.graceful_degradation import ServiceHealthChecker`
2. `__init__` 中初始化:
```python
self.health_checker = ServiceHealthChecker()  # 无参数
```

**pre_model.py 改动**:
1. `build_pre_model_hook` 新增 `health_checker` 参数
2. 在速率限制检查后插入:
```python
if health_checker and not health_checker.is_healthy("llm"):
    return {
        "messages": [{"role": "assistant", "content": "[System degraded] LLM 服务不可用"}],
        "task_status": "degraded",
    }
```

**验证**: mock `health_checker.is_healthy` 返回 `False` → pre_model_hook 返回降级 dict

---

### Step 6: 审计日志 ⚠️ 需修正

**⚠️ 问题**: `audit_logger.log()` **不存在**。实际 API 是 `audit_logger.log_error(error, trace_id=..., ...)`。接受 error dict 而非命名参数 event。

**文件**: `src/rect_agent/hooks/post_model.py`

**改动**:
1. 新增导入:
```python
from src.agent.audit_logger import audit_logger
```
2. 在 `step_count` 递增后、返回前插入:
```python
try:
    tool_names = []
    if messages:
        last = messages[-1]
        tcs = getattr(last, "tool_calls", None)
        if tcs:
            tool_names = [t.get("name") for t in (tcs if isinstance(tcs, list) else [])]

    audit_logger.log_error(
        error={"error_code": "LLM_CALL", "error_type": "RECOVERABLE", "retryable": False},
        trace_id=state.get("trace_id", ""),
        thread_id=state.get("thread_id", ""),
        context={"step": step_count + 1, "tool_calls": tool_names, "status": "completed"},
    )
except Exception:
    logger.warning("[PostModel] Audit log failed", exc_info=True)
```

**注意**: 不阻断主流程，审计日志失败只记录 warning。

**验证**: mock `audit_logger.log_error` → 确认被调用且不抛异常

---

### Step 7: 重试前预算校验 ✅ 通过

**文件**: `src/rect_agent/middleware/tool_wrapper.py`

**改动**:
1. 新增 `_check_budget` 函数:
```python
def _check_budget(estimated_cost: float, tool_name: str) -> bool:
    limiter = get_rate_limiter()
    ok, msg = limiter.check_cost_limit()
    if not ok:
        logger.warning(f"[ToolWrapper] Budget exceeded for {tool_name}: {msg}")
    return ok
```
2. 在重试循环前调用:
```python
if not _check_budget(delay * 0.01, tool_name):
    return ToolMessage(content="预算不足，跳过重试", tool_call_id=tool_call_id, status="error")
```

**验证**: mock `check_cost_limit` 返回 `(False, "msg")` → 工具返回 `status="error"` 不执行

---

## Phase 3 — 中影响，中高工作量

---

### Step 11: 幂等 SQLite 持久化 ⚠️ 需修正

**⚠️ 问题**: `load_tool_result`/`save_tool_result` **不在** `src.agent.tools.data` 中（该模块不存在）。它们在 `LongTermManager` 上作为方法存在:
- `LongTermManager.load_tool_result(thread_id, tool_call_id) → dict | None`
- `LongTermManager.save_tool_results(thread_id, results: list[dict])`

**文件**: `src/rect_agent/middleware/tool_wrapper.py`

**改动**:
1. 通过 `RectContext.long_term` 或全局实例获取:
```python
def _get_long_term(ctx: RectContext | None = None):
    if ctx and ctx.long_term:
        return ctx.long_term
    # fallback: 需要全局 LongTermManager 实例
    from src.agent.context.long_term import LongTermManager
    return LongTermManager()  # 简化，实际需要配置
```
2. 在 `_check_idempotency` 内存缓存之后、执行之前:
```python
mgr = _get_long_term(ctx)
persisted = mgr.load_tool_result(thread_id, tool_call_id)
if persisted:
    content = persisted.get("content", "")
    _idempotency_cache[tool_call_id] = content
    return ToolMessage(content=content, tool_call_id=tool_call_id, status="success")
```
3. 在成功执行后:
```python
mgr.save_tool_results(thread_id, [{"tool_call_id": tool_call_id, "tool_name": tool_name, "content": content}])
```

**验证**: mock `LongTermManager.load_tool_result` 返回 mock dict → 工具返回缓存内容，跳过执行

---

### Step 12: 早停检测 ✅ 通过

**文件**: `src/rect_agent/hooks/post_model.py`

**改动**:
1. 新增常量 + 检测函数:
```python
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
```
2. 在 `post_model_hook` 的 `step_count` 递增后插入:
```python
if _detect_final_answer(messages):
    updates["task_status"] = "completed"
    updates["current_action"] = "early_stop:final_answer"
if _detect_homogeneous_tool_calls(messages):
    updates["task_status"] = "completed"
    updates["current_action"] = "early_stop:homogeneous_loop"
if state.get("step_count", 0) >= 25:
    updates["task_status"] = "completed"
    updates["current_action"] = "early_stop:max_steps"
```

**验证**: 构造包含 "final answer" 的消息列表 → `_detect_final_answer` 返回 True；构造 3 次相同工具调用 → `_detect_homogeneous_tool_calls` 返回 True

---

### Step 9: RectTool 统一封装 ⚠️ 需修正

**⚠️ HITL 冲突**: `post_model_hook` 已通过 `interrupt()` 拦截 `CRITICAL_TOOLS`。`RectTool.requires_approval` 会创建**第二道审批门**。必须明确分层：`post_model_hook` 的 `interrupt()` 是**系统级 HITL**（拦截所有关键工具），`RectTool.requires_approval` 是**工具级 HITL**（仅特定工具，不触发系统中断）。

**⚠️ 循环导入风险**: `rect_tool.py` 导入 `_check_critical_tools` 从 `post_model.py`。如果 `post_model.py` 未来导入 `rect_tool.py` 则形成循环。建议提取 `CRITICAL_TOOLS` 和 `_check_critical_tools` 到共享模块。

**文件**: `src/rect_agent/middleware/rect_tool.py` (新文件), `src/rect_agent/shared.py` (新文件)

**先创建 `src/rect_agent/shared.py`**:
```python
"""共享常量和工具函数，避免 hooks/ 和 middleware/ 之间的循环导入。"""

# 从 hooks/post_model.py 迁移至此
CRITICAL_TOOLS = {"execute_code", "write_file", "bash", "code_execution", "write_operation", "resource_access", "file_write", "file_read"}

def check_critical_tools(state: dict) -> list[str]:
    messages = state.get("messages", [])
    if not messages:
        return []
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or (last.get("tool_calls") if isinstance(last, dict) else None)
    if not tool_calls:
        return []
    return [tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "") for tc in tool_calls if (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")) in CRITICAL_TOOLS]
```

**新文件 `middleware/rect_tool.py`**:
```python
from dataclasses import dataclass
from typing import Any, Callable
from pydantic import BaseModel
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from src.rect_agent.middleware.context import RectContext
from src.rect_agent.middleware.tool_wrapper import _check_idempotency, _record_idempotency
from src.rect_agent.shared import CRITICAL_TOOLS
from src.agent.retry_handler import ToolRetryConfig
from src.agent.schemas.agent_protocol import StructuredAgentError
from src.agent.human_in_loop import ApprovalType, request_approval
import time


@dataclass
class RectTool:
    function: Callable
    name: str
    description: str
    parameters_schema: type[BaseModel] | None = None
    max_retries: int = ToolRetryConfig.max_retries
    requires_approval: bool = False  # 工具级HITL (post_model_hook 的系统级 interrupt 独立于此)
    timeout: float = 30.0

    def execute(self, request: ToolCallRequest, ctx: RectContext | None = None) -> ToolMessage:
        tc = request.tool_call
        tool_call_id = tc.get("id", "") or ""
        tool_name = self.name

        cached = _check_idempotency(tc)
        if cached:
            return ToolMessage(content=cached, tool_call_id=tool_call_id, status="success")

        tool_breakers = ctx.tool_breakers if ctx else get_tool_breakers()
        if not tool_breakers.can_execute(tool_name):
            return ToolMessage(content=f"断路器已开启，跳过 {tool_name}", tool_call_id=tool_call_id, status="error")

        if self.requires_approval:
            try:
                result = request_approval(ApprovalType.CODE_EXECUTION, tool_name)
                if not result.approved:
                    return ToolMessage(content=f"工具 {tool_name} 被拒绝", tool_call_id=tool_call_id, status="rejected")
            except Exception:
                return ToolMessage(content="审批排队", tool_call_id=tool_call_id, status="pending")

        delay = ToolRetryConfig.initial_delay
        for attempt in range(self.max_retries + 1):
            try:
                result = self.function(request)
                content = str(result.content) if hasattr(result, "content") else str(result)
                tool_breakers.record_success(tool_name)
                _record_idempotency(tc, content)
                return ToolMessage(content=content, tool_call_id=tool_call_id, status="success")
            except StructuredAgentError as e:
                if not e.envelope.retryable or attempt >= self.max_retries:
                    tool_breakers.record_failure(tool_name)
                    raise
                time.sleep(delay)
                delay *= ToolRetryConfig.backoff_factor
            except Exception:
                if attempt >= self.max_retries:
                    tool_breakers.record_failure(tool_name)
                    break
                time.sleep(delay)
                delay *= ToolRetryConfig.backoff_factor
        return ToolMessage(content="工具执行失败", tool_call_id=tool_call_id, status="error")
```

**注意**: `RectTool` 与现有 `production_tool_wrapper` 函数并存。Phase 3 结束时逐步迁移，完成后删除旧函数。

**验证**: 新建 `RectTool(name="test", function=MagicMock())` → `execute(MagicMock())` → 走 idempotency→breaker→retry 全流程

---

### Step 10: MemoryManager 外观 ⚠️ 需修正

**⚠️ 核心问题**: `retrieve()` 是 `async` 方法，但 `pre_model_hook` 和 `post_model_hook` 都是**同步函数**（LangGraph 同步调用）。调用 `await retrieve()` 在同步函数中会产生 `RuntimeWarning: coroutine was never awaited`。

**修正**: 全部改为同步接口。

**文件**: `src/rect_agent/memory_manager.py` (新文件)

```python
import logging
from src.agent.context.long_term import LongTermManager
from src.agent.context.compression import ContextCompressor


class MemoryManager:
    """分层记忆系统，统一 L1-L4 接口。
    
    全部为同步接口，兼容 LangGraph hook 的执行模型。
    """

    def __init__(self, long_term: LongTermManager, compressor: ContextCompressor):
        self._lt = long_term
        self._compressor = compressor

    def retrieve(self, user_id: str, thread_id: str, top_k: int = 3) -> list:
        """检索 L2+L3 层记忆。L1 (工作记忆) 在 State.messages 中。"""
        contexts = []
        try:
            docs = self._lt.search_similar(user_id, thread_id, top_k=top_k)
            if docs:
                contexts.extend(list(docs))
        except Exception:
            logging.getLogger(__name__).warning("[MemoryManager] Memory retrieval failed", exc_info=True)
        return contexts

    def store_session(self, thread_id: str, messages: list):
        """持久化 L2 会话。"""
        try:
            self._lt.save_session(thread_id, messages)
        except Exception:
            logging.getLogger(__name__).warning("[MemoryManager] Session store failed", exc_info=True)

    def compress(self, messages: list, token_usage: dict, compression_count: int):
        """L1 工作记忆压缩。返回 (compressed_msgs, new_count)。"""
        percentage = token_usage.get("percentage", 0)
        if percentage < 70 or compression_count >= 5:
            return None, compression_count
        try:
            result = self._compressor.compress(context={"messages": messages})
            if result and result.summary_message:
                return [result.summary_message], compression_count + 1
        except Exception:
            logging.getLogger(__name__).warning("[MemoryManager] Compression failed", exc_info=True)
        return None, compression_count
```

**agent.py 集成**:
```python
from src.rect_agent.memory_manager import MemoryManager
self.memory = MemoryManager(long_term=self.long_term, compressor=self.compressor)

# pre_model_hook 中: self.memory.compress(messages, state["token_usage"], state["compression_count"])
# post_model_hook 中: self.memory.store_session(thread_id, messages)
```

**验证**: 构造 mock `LongTermManager` + mock `ContextCompressor` → `retrieve("u1", "t1")` 返回列表

---

## 验证清单

### Phase 1

| 步骤 | 验证命令 | 预期 |
|------|---------|------|
| 1 | `python -c "from src.rect_agent.graph import graph; print(graph.checkpointer is not None)"` | `True` |
| 2 | `python -m pytest tests/test_rect_agent.py -v -k "agent" --tb=short` | All passed |
| 3 | `python -c "from src.rect_agent import RectAgent; a = RectAgent(llm=None, output_type=str); print(type(a).__name__)"` | `RectAgent` |
| 4 | 全量测试 | `python -m pytest tests/test_rect_agent.py -v --tb=short` → 18 passed |

### Phase 2

| 步骤 | 验证命令 | 预期 |
|------|---------|------|
| 8 | `python -c "from src.rect_agent.middleware.context import RectContext; ctx=RectContext(); print(ctx.rate_limiter is not None)"` | `True` |
| 5 | 新增测试: mock `health_checker.is_healthy=False` | 返回 degraded 响应 |
| 6 | 新增测试: mock `audit_logger.log_error` | 被调用，不抛异常 |
| 7 | 新增测试: mock `check_cost_limit=(False,"")` | 返回 budget error |

### Phase 3

| 步骤 | 验证命令 | 预期 |
|------|---------|------|
| 11 | 新增测试: mock `load_tool_result` | 返回缓存内容 |
| 12 | 新增测试: 构造 "final answer" 消息 | `_detect_final_answer` True |
| 9 | 新增测试: `RectTool(name="test", function=mock)` | `.execute()` 走全流程 |
| 10 | 新增测试: `MemoryManager(long_term=mock, compressor=mock)` | `retrieve()` 返回 list |

---

## 全阶段进度跟踪

- [ ] **Phase 1** (~28 行)
  - [ ] Step 1: graph.py 检查点 (⚠️ 用 `SqliteSaver(sqlite3.connect(...))`)
  - [ ] Step 2: agent.py LLM 重试 (⚠️ 自定义 `retry_if_exception_type` + mock fallback)
  - [ ] Step 3: agent.py + __init__.py output_type (⚠️ 处理 `str` 分支)
  - [ ] Step 4: middleware/tool_wrapper.py trace_id 透传
- [ ] **Phase 2** (~50 行)
  - [ ] Step 8: RectContext 轻量注入 (先做)
  - [ ] Step 5: 优雅降级集成 (⚠️ `ServiceHealthChecker()` 无参)
  - [ ] Step 6: 审计日志 (⚠️ 用 `log_error()` 非 `log()`)
  - [ ] Step 7: 重试前预算校验
- [ ] **Phase 3** (~135 行)
  - [ ] Step 11: 幂等 SQLite 持久化 (⚠️ 用 `LongTermManager.load_tool_result`)
  - [ ] Step 12: 早停检测
  - [ ] Step 9: RectTool 统一封装 (⚠️ 提取 shared.py 避免循环导入)
  - [ ] Step 10: MemoryManager 外观 (⚠️ 全部同步接口)
- [ ] **全阶段测试**: `python -m pytest tests/test_rect_agent.py -v --tb=short` → All passed

### Step 2: agent.py — LLM 重试 (with_retry + breaker 联动)

**方法**: `RunnableLambda(breaker_check) | llm.with_retry()`，breaker open 时不重试直接抛异常。

**文件**: `src/rect_agent/agent.py`

**改动**:
1. 新增导入:
   - `from langchain_core.runnables import RunnableLambda`
   - `from src.agent.schemas.agent_protocol import StructuredAgentError, ErrorLevel`
2. 在 `__init__` 之前新增 `_build_llm_with_breaker()` 方法
3. `_build_graph` 中将 `model=self.llm` 替换为 `model=self._build_llm_with_breaker`

**逻辑**:
```
llm_input → breaker can_execute? → NO → 抛 StructuredAgentError(LLM_CIRCUIT_OPEN)
                                 → YES → llm 调用 (with_retry 最多 4 次)
```

**注意**: `with_retry` 重试所有 `Exception`，不重试 `StructuredAgentError`（从中断器抛出的会立即失败）。

### Step 3: agent.py + __init__.py — output_type 泛型

**方法**: `Generic[OutputT]` + `invoke` 出口 `model_validate`

**文件**: `src/rect_agent/agent.py`, `src/rect_agent/__init__.py`

**agent.py 改动**:
1. 新增导入: `from typing import Generic, TypeVar`
2. 新增变量: `OutputT = TypeVar("OutputT", bound=BaseModel | str)`
3. 类签名: `class RectAgent(Generic[OutputT]):`
4. `__init__` 新增参数 `output_type: type[OutputT] = str`
5. `invoke` 方法改为 `def invoke(self, input_data: dict, config: dict | None = None) -> OutputT:`，出口校验

**__init__.py 改动**:
1. 新增导出 `OutputT`

**设计决策**:
- 使用 `model_validate_json` 而非 `model_validate`：LLM 返回的是 JSON 字符串
- 只在校验最后一条 AI 消息，不对历史消息校验
- 不侵入 `create_react_agent` 内部（它不支持 output_type 参数）

### Step 4: middleware/tool_wrapper.py — trace_id 透传

**方法**: 从 `request.state` 或 `tool_call.args` 取 trace_id

**文件**: `src/rect_agent/middleware/tool_wrapper.py`

**改动**:
1. 第 36 行 `start_time` 之后，新增 `trace_id` 提取
2. 第 79-86 行 `StructuredAgentError` 构造使用提取的 `trace_id`

**优先级顺序**:
1. `(request.state or {}).get("trace_id", "")` — LangGraph 运行时 state
2. `tc.get("args", {}).get("__trace_id", "")` — 工具参数中带
3. 兜底空字符串

## 验证清单

| 步骤 | 验证命令 | 预期 |
|------|---------|------|
| 1 | `python -c "from src.rect_agent.graph import graph; print(graph.checkpointer is not None)"` | `True` |
| 2 | `python -m pytest tests/test_rect_agent.py -v -k "agent" --tb=short` | All passed |
| 3 | `python -c "from src.rect_agent import RectAgent; a = RectAgent(llm=None); print(type(a).__name__)"` | `RectAgent` |
| 4 | 全量测试 | `python -m pytest tests/test_rect_agent.py -v --tb=short` → 18 passed |

## Phase 2 — 高影响，中工作量

| # | 改进项 | 文件 | 改动量 | 说明 |
|---|--------|------|--------|------|
| 5 | 优雅降级集成 | `agent.py` + `hooks/pre_model.py` | ~20 行 | 接入 `graceful_degradation.py` 健康检查和降级判定 |
| 6 | 审计日志 | `hooks/post_model.py` | ~5 行 | 调用 `audit_logger.py` 记录 LLM 调用和工具执行 |
| 7 | 重试前预算校验 | `middleware/tool_wrapper.py` | ~8 行 | 重试前检查 `remaining_budget > estimated_retry_cost` |
| 8 | `RectContext` 轻量注入 | `middleware/context.py` 新文件 | ~15 行 | `@dataclass RectContext` 封装依赖，闭包传入 tools/wrapper.py |

---

### Step 5: 优雅降级集成

**文件**: `src/rect_agent/agent.py`, `src/rect_agent/hooks/pre_model.py`

**方法**: 在 `pre_model_hook` 中接入 `ServiceHealthChecker`，熔断或降级时返回降级响应而非抛异常。

**agent.py 改动**:
1. 新增导入 `from src.agent.graceful_degradation import ServiceHealthChecker`
2. `__init__` 中初始化 `self.health_checker = ServiceHealthChecker(failure_threshold=3)`

**pre_model.py 改动**:
1. `build_pre_model_hook` 新增 `health_checker` 参数
2. 在速率限制检查后、LLM 调用前插入健康检查:

```python
if health_checker and not health_checker.is_healthy("llm"):
    # 降级模式：跳过 LLM 调用，返回降级响应
    return {
        "messages": [{"role": "assistant", "content": "[System degraded] LLM 服务不可用，跳过推理"}],
        "task_status": "degraded",
    }
```

**验证**: mock `health_checker.is_healthy` 返回 `False`，确认 pre_model_hook 返回降级消息。

---

### Step 6: 审计日志

**文件**: `src/rect_agent/hooks/post_model.py`

**方法**: 在 `post_model_hook` 中调用 `audit_logger.py` 记录请求。

**改动**:
1. 新增导入 `from src.agent.audit_logger import audit_logger`
2. 在 `step_count` 递增后、返回前插入:

```python
try:
    audit_logger.log(
        event_type="llm_call",
        trace_id=state.get("trace_id", ""),
        step=step_count + 1,
        tool_calls=[t.get("name") for t in (getattr(messages[-1], "tool_calls", []) if messages else [])],
        status="completed",
    )
except Exception:
    logger.warning("[PostModel] Audit log failed", exc_info=True)
```

**注意**: 不阻断主流程，审计日志失败只记录 warning。

---

### Step 7: 重试前预算校验

**文件**: `src/rect_agent/middleware/tool_wrapper.py`

**方法**: 在重试循环前检查剩余预算是否足够覆盖下次重试。

**改动**:
1. 从 `request.state` 或 `get_rate_limiter()` 读取当前成本
2. 新增 `_check_budget()` 函数:

```python
def _check_budget(estimated_cost: float, tool_name: str) -> bool:
    limiter = get_rate_limiter()
    ok, _ = limiter.check_cost_limit()
    if not ok:
        logger.warning(f"[ToolWrapper] Budget exceeded, skipping {tool_name}")
        return False
    return True
```

3. 在重试循环前调用，预算不足时直接返回 error 消息不重试:

```python
if not _check_budget(delay * 0.01, tool_name):  # 粗略估计重试成本
    return ToolMessage(content="预算不足，跳过重试", tool_call_id=tool_call_id, status="error")
```

---

### Step 8: RectContext 轻量注入

**文件**: `src/rect_agent/middleware/context.py` (新文件), `src/rect_agent/tools/wrapper.py`

**方法**: dataclass 封装依赖，通过 `build_tool_node()` 闭包注入。

**新文件 `middleware/context.py`**:

```python
from dataclasses import dataclass, field
from src.agent.rate_limiter import RateLimiter, ToolCircuitBreaker, get_rate_limiter, get_tool_breakers
from src.agent.config import AgentConfig
from src.agent.graceful_degradation import ServiceHealthChecker


@dataclass
class RectContext:
    """有限范围的依赖上下文，不替代 LangGraph State。"""
    rate_limiter: RateLimiter = field(default_factory=get_rate_limiter)
    tool_breakers: ToolCircuitBreaker = field(default_factory=get_tool_breakers)
    config: AgentConfig | None = None
    health_checker: ServiceHealthChecker | None = None
```

**tools/wrapper.py 改动**:
1. 新增导入 `from src.rect_agent.middleware.context import RectContext`
2. `build_tool_node()` 新增 `ctx: RectContext | None = None` 参数
3. `production_tool_wrapper` 改为闭包捕获 `ctx`:

```python
def build_tool_node(ctx: RectContext | None = None) -> ToolNode:
    def _wrapper(request: ToolCallRequest, execute: Callable) -> ToolMessage:
        # 使用 ctx 中的依赖，无 ctx 时 fallback 到全局函数
        return production_tool_wrapper(request, execute, ctx=ctx)
    return ToolNode(TOOLS, handle_tool_errors=False, wrap_tool_call=_wrapper)
```

**`production_tool_wrapper` 签名调整**:

```python
def production_tool_wrapper(
    request: ToolCallRequest,
    execute: Callable,
    ctx: RectContext | None = None,
) -> ToolMessage:
    rate_limiter = ctx.rate_limiter if ctx else get_rate_limiter()
    tool_breakers = ctx.tool_breakers if ctx else get_tool_breakers()
    # ... 使用 rate_limiter / tool_breakers 替代全局函数调用
```

---

## Phase 3 — 中影响，中高工作量

| # | 改进项 | 文件 | 改动量 | 说明 |
|---|--------|------|--------|------|
| 9 | `RectTool` 统一封装 | `middleware/rect_tool.py` 新文件 | ~60 行 | 参数校验 + 重试 + HITL 一体化的工具 dataclass |
| 10 | `MemoryManager` 外观 | `memory_manager.py` 新文件 | ~50 行 | 统一 L1-L4 记忆接口 |
| 11 | 幂等 SQLite 持久化 | `middleware/tool_wrapper.py` | ~10 行 | 复用 `load_tool_result`/`save_tool_result` |
| 12 | 早停检测 | `hooks/post_model.py` | ~15 行 | 移植 Final Answer + 同质调用检测 |

---

### Step 9: RectTool 统一封装

**文件**: `src/rect_agent/middleware/rect_tool.py` (新文件)

**方法**: 将 `production_tool_wrapper` 的函数式包装改为 `RectTool` dataclass，纳入参数校验、HITL 门控。

```python
from dataclasses import dataclass, field
from typing import Any, Callable
from pydantic import BaseModel
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.rect_agent.middleware.context import RectContext
from src.rect_agent.middleware.tool_wrapper import _check_idempotency, _record_idempotency, _check_budget
from src.rect_agent.hooks.post_model import _check_critical_tools, CRITICAL_TOOLS
from src.agent.retry_handler import ToolRetryConfig
from src.agent.schemas.agent_protocol import ERROR_CODES, StructuredAgentError
from src.agent.human_in_loop import ApprovalType, request_approval


@dataclass
class RectTool:
    function: Callable
    name: str
    description: str
    parameters_schema: type[BaseModel] | None = None
    max_retries: int = ToolRetryConfig.max_retries
    requires_approval: bool = False
    timeout: float = 30.0

    def execute(self, request: ToolCallRequest, ctx: RectContext | None = None) -> ToolMessage:
        tc = request.tool_call
        tool_call_id = tc.get("id", "") or ""
        tool_name = self.name

        # 1. 幂等缓存
        cached = _check_idempotency(tc)
        if cached:
            return ToolMessage(content=cached, tool_call_id=tool_call_id, status="success")

        # 2. 熔断检查
        tool_breakers = ctx.tool_breakers if ctx else get_tool_breakers()
        if not tool_breakers.can_execute(tool_name):
            return ToolMessage(content=f"熔断器已开启，跳过 {tool_name}", tool_call_id=tool_call_id, status="error")

        # 3. 预算校验
        if not _check_budget(0.01, tool_name):
            return ToolMessage(content="预算不足，跳过", tool_call_id=tool_call_id, status="error")

        # 4. HITL
        if self.requires_approval:
            state = getattr(request, "state", {})
            # 复用 _check_critical_tools 逻辑
            critical = _check_critical_tools({"messages": [{"tool_calls": [tc]}]})
            if critical:
                try:
                    result = request_approval(ApprovalType.CODE_EXECUTION, tool_name)
                    if not result.approved:
                        return ToolMessage(content=f"工具 {tool_name} 被拒绝", tool_call_id=tool_call_id, status="rejected")
                except Exception:
                    return ToolMessage(content="审批排队，稍后重试", tool_call_id=tool_call_id, status="pending")

        # 5. 重试执行
        import time
        delay = ToolRetryConfig.initial_delay
        for attempt in range(self.max_retries + 1):
            try:
                result = self.function(request)
                content = str(result.content) if hasattr(result, "content") else str(result)
                tool_breakers.record_success(tool_name)
                _record_idempotency(tc, content)
                return ToolMessage(content=content, tool_call_id=tool_call_id, status="success")
            except StructuredAgentError as e:
                if not e.envelope.retryable or attempt >= self.max_retries:
                    tool_breakers.record_failure(tool_name)
                    raise
                time.sleep(delay)
                delay *= ToolRetryConfig.backoff_factor
            except Exception as e:
                if attempt >= self.max_retries:
                    tool_breakers.record_failure(tool_name)
                    break
                time.sleep(delay)
                delay *= ToolRetryConfig.backoff_factor

        return ToolMessage(content="工具执行失败", tool_call_id=tool_call_id, status="error")
```

**注意**: `RectTool` 类与现有的 `production_tool_wrapper` 函数并存，逐步迁移。Phase 3 结束时再删除旧函数。

---

### Step 10: MemoryManager 外观

**文件**: `src/rect_agent/memory_manager.py` (新文件)

**方法**: 包装 `LongTermManager` + `ContextCompressor` + `CompressedTurn` 为统一接口。

```python
from dataclasses import dataclass
from typing import Any

from src.agent.context.long_term import LongTermManager, LongTermConfig
from src.agent.context.compression import ContextCompressor, CompressionConfig


class WorkingMemory:
    def has_relevant(self, query: str) -> bool:
        return bool(query)

    def get(self) -> dict:
        return {"type": "working_memory"}


class SessionMemory:
    def __init__(self, long_term: LongTermManager):
        self._lt = long_term

    async def get_context(self, query: str) -> dict | None:
        return None  # 当前会话上下文在 State.messages 中

    async def store(self, thread_id: str, messages: list):
        self._lt.save_session(thread_id, messages)


class VectorMemory:
    def __init__(self, long_term: LongTermManager):
        self._lt = long_term

    async def search(self, query: str, user_id: str, thread_id: str, top_k: int = 3) -> list:
        return list(self._lt.search_similar(user_id, thread_id, top_k=top_k))

    async def store(self, text: str, metadata: dict | None = None):
        pass  # 暂用 LongTermManager 现有存储


@dataclass
class MemoryManager:
    """分层记忆系统，统一 L1-L4 接口。"""
    long_term: LongTermManager
    compressor: ContextCompressor

    def __post_init__(self):
        self.working = WorkingMemory()
        self.session = SessionMemory(self.long_term)
        self.cross_session = VectorMemory(self.long_term)

    async def retrieve(self, query: str, user_id: str, thread_id: str, level: int = 3) -> list:
        contexts = []
        if level >= 2:
            ctx = await self.session.get_context(query)
            if ctx:
                contexts.append(ctx)
        if level >= 3:
            docs = await self.cross_session.search(query, user_id, thread_id, top_k=3)
            if docs:
                contexts.extend(docs)
        return contexts

    def compress(self, messages: list, compression_count: int) -> tuple[list | None, int]:
        import logging
        logger = logging.getLogger(__name__)
        token_usage = {"percentage": 75}  # 简化，实际从 State 读取
        if token_usage.get("percentage", 0) >= 70 and compression_count < 5:
            try:
                result = self.compressor.compress(context={"messages": messages})
                if result and result.summary_message:
                    return [result.summary_message], compression_count + 1
            except Exception:
                logger.warning("[MemoryManager] Compression failed", exc_info=True)
        return None, compression_count
```

**agent.py 集成**:

```python
# __init__ 中
from src.rect_agent.memory_manager import MemoryManager
self.memory = MemoryManager(long_term=self.long_term, compressor=self.compressor)

# hooks 中通过闭包使用 self.memory 替代 self.long_term + self.compressor
```

---

### Step 11: 幂等 SQLite 持久化

**文件**: `src/rect_agent/middleware/tool_wrapper.py`

**方法**: 复用原 `src/agent/tools/` 的 `load_tool_result`/`save_tool_result` 跨会话去重。

**改动**:
1. 新增导入: `from src.agent.tools.data import load_tool_result, save_tool_result`
2. 在 `_check_idempotency` 内存缓存之后、执行之前，新增 SQLite 检查:

```python
# 在 production_tool_wrapper 中
# 内存缓存未命中 → 查 SQLite
persisted = load_tool_result(thread_id, tool_call_id)
if persisted:
    _idempotency_cache[tool_call_id] = persisted.content
    return ToolMessage(content=persisted.content, tool_call_id=tool_call_id, status="success")
```

3. 在成功执行后，写入 SQLite:

```python
save_tool_result(thread_id, tool_call_id, tool_name, content)
```

**注意**: 需要 `thread_id` — 从 `request.state` 获取或从 `tc.args` 提取。

---

### Step 12: 早停检测

**文件**: `src/rect_agent/hooks/post_model.py`

**方法**: 从原 `agent.py:_should_continue` 移植 3 种检测。

```python
FINAL_ANSWER_MARKERS = {
    "zh": ["最终答案", "综上所述", "总结"],
    "en": ["final answer", "in summary", "to summarize"],
}

def _detect_final_answer(messages: list) -> bool:
    """检测 LLM 是否输出了 Final Answer 标记。"""
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
    """检测同一工具同参数连续调用 3 次。"""
    recent_tools = []
    for m in reversed(messages[-10:]):
        tcs = getattr(m, "tool_calls", None)
        if not tcs and isinstance(m, dict):
            tcs = m.get("tool_calls")
        if tcs:
            for tc in tcs:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                recent_tools.append((name, str(args)))
    if len(recent_tools) >= 3:
        last_three = recent_tools[-3:]
        if len(set(t[0] for t in last_three)) == 1 and len(set(t[1] for t in last_three)) == 1:
            return True
    return False
```

**post_model_hook 集成**: 在 `step_count` 递增后、返回前：

```python
# 早停检测
if _detect_final_answer(messages):
    updates["task_status"] = "completed"
    updates["current_action"] = "early_stop:final_answer"
    logger.info("[PostModel] Early stop triggered by Final Answer")

if _detect_homogeneous_tool_calls(messages):
    updates["task_status"] = "completed"
    updates["current_action"] = "early_stop:homogeneous_loop"
    logger.info("[PostModel] Early stop triggered by homogeneous tool calls")
```

---

## 全阶段执行优先级

| 阶段 | 步骤 | 影响 | 工作量 | 推荐顺序 |
|------|------|------|--------|---------|
| **Phase 1** | 1-4: 检查点/LLM重试/output_type/trace_id | 高 | 低 ~23 行 | **先做** |
| **Phase 2** | 5-8: 优雅降级/审计/预算校验/RectContext | 高 | 中 ~50 行 | 2 |
| **Phase 3** | 9-10: RectTool/MemoryManager | 中 | 高 ~110 行 | 3 |
| **Phase 3** | 11-12: 幂等SQLite/早停检测 | 中 | 中 ~25 行 | 4 |

**推荐执行顺序**: Phase 1 → Phase 2 → Step 11 → Step 12 → Step 9 → Step 10

从最快见效的开始（检查点+重试），逐步加深到统一封装。

## 全阶段进度跟踪

- [ ] **Phase 1**
  - [ ] Step 1: graph.py 检查点
  - [ ] Step 2: agent.py LLM 重试
  - [ ] Step 3: agent.py + __init__.py output_type 泛型
  - [ ] Step 4: middleware/tool_wrapper.py trace_id 透传
- [ ] **Phase 2**
  - [ ] Step 5: 优雅降级集成
  - [ ] Step 6: 审计日志
  - [ ] Step 7: 重试前预算校验
  - [ ] Step 8: RectContext 轻量注入
- [ ] **Phase 3**
  - [ ] Step 9: RectTool 统一封装
  - [ ] Step 10: MemoryManager 外观
  - [ ] Step 11: 幂等 SQLite 持久化
  - [ ] Step 12: 早停检测
- [ ] 全阶段测试验证
