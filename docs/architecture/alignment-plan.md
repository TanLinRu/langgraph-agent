# 代码架构对齐方案

> 基于 `docs/architecture/agent-flow-design.md` 规范，对全栈代码进行分阶段整改。
>
> **目标**: 统一错误处理协议、接入重试熔断机制、结构化 Agent 输入输出契约、消除吞没异常。

---

## 📊 总体范围

| 阶段 | 整改目标 | 涉及文件 | 测试文件 |
|------|---------|---------|---------|
| P1 | 基础协议层 (ErrorEnvelope, schemas/) | 6 | 2 |
| P2 | Agent 层对齐 (run契约, max_steps, HITL) | 4 | 3 |
| P3 | 上下文系统对齐 (压缩错误, 存储异常) | 3 | 2 |
| P4 | 工具层对齐 (结构化ToolResult, 幂等键) | 2 | 2 |
| P5 | Supervisor/Orchestrator 对齐 (重试+错误包装) | 3 | 2 |
| P6 | ACP/CLI 对齐 (错误格式统一) | 3 | 1 |
| P7 | API 层对齐 (统一错误中间件) | 1 | 1 |
| P8 | 测试覆盖补齐 | — | 8 |

---

## 📐 验收标准总览

- [ ] 全库无 `except: pass` / `except Exception: continue` 吞没异常（仅 3 处见 T6-T8）
- [ ] 所有 LLM 调用通过 `@retry_with_backoff` 装饰器包装
- [ ] 所有工具调用通过幂等键 + CircuitBreaker 检查
- [ ] `Agent.run()` 返回 `AgentOutput` 结构 (含 `status`, `trace_log`, `error`)
- [ ] `supervisor.run()` 返回结构化错误 (含 `error_code`, `error_type`)
- [ ] `ToolResult` 结构化 (非 flat string)
- [x] ~~`HumanInTheLoop` approval 逻辑修复 (`asyncio.Event.wait()` 返回布尔值)~~ → ⚠️ **P0 Bug，尚未修复**
- [ ] FastAPI 统一使用一种错误响应格式
- [ ] 新增测试覆盖率: retry_handler, error_envelope, agent_protocol, human_in_loop

> ⚠️ **代码审查修正**: alignment-plan.md 初稿存在以下不准确：
> - "全库 66+ 处 try/except Exception" — 实际仅 3 处真正需要修复的吞没异常
> - "compression.py L199 except Exception: pass" — 实际为 `logger.warning()` + 隐式 return，并非 pass
> - `ErrorEnvelope` 12字段描述 — 实际 `agent.py` 只有 6 字段的简化 `AgentError`
> - "max_iterations 已实现" — 实际只有硬编码 `MAX_ITERATIONS=50`，无配置项
> - `CompressionResult.errors` 字段 — 实际不存在
> - T4 循环依赖：retry_handler → schemas/ → T1 创建 schemas/

---

## ⚠️ 补充说明（v2 审查后追加）

### 1. `schemas/__init__.py` 需随 T19 更新
T2 创建 `schemas/__init__.py` 时未包含 `tool_result.py`。T19 创建 `schemas/tool_result.py` **后，必须同步更新 `schemas/__init__.py`** 导出 `ToolResult`。

```python
# T19 完成后，在 schemas/__init__.py 添加:
from .tool_result import ToolResult
__all__.extend(["ToolResult"])
```

### 2. P3 压缩返回类型变更 — 波及调用者
T17 将 `compress()` 返回类型从 `list` **改为 `CompressionResult`**，以下调用点需同步更新：

| 位置 | 改动 |
|------|------|
| `agent.py:_node_compress` | 解包 `result.compressed_messages` 而非直接用 result |
| `agent.py` 中所有 `compressor.compress()` 调用 | 解包新结构 |
| 测试代码中 mock `compress()` 返回值 | 改为返回 `CompressionResult` |

### 3. 幂等键缓存存储位置
T21 的 `_cache_idempotent_result()` / `_get_idempotent_result()` 未指定后端：

```
存储: Agent 实例级 dict（内存）
  ├── _idempotent_cache: dict[str, dict]  # tool_call_id → result
  ├── TTL: 不主动过期（session 生命周期内有效）
  ├── 上限: 最多缓存 1000 条，超过时淘汰最早条目
  └── 线程安全: threading.Lock 保护
```

### 4. 边界情况补充

| 场景 | 处理策略 | 优先级 |
|------|---------|--------|
| `OPENAI_API_KEY` 缺失 | `_get_or_create_trace_id` 使用 `uuid4()` 回退 | P0 |
| Python 3.10+ 兼容 | `X \| None` 语法 → `Optional[X]` | P1 |
| 现有调用者迁移 | `main.py`、`graph.py`、`opencode_agent.py` 中 `run()` 返回值处理 | P2 |
| 多线程安全 | `_idempotent_cache` 使用 `threading.Lock` | P2 |

### 5. 测试优先级标注

| 文件 | 业务范畴 | 优先级 |
|------|---------|--------|
| `tests/test_error_envelope.py` | Unit | P0 |
| `tests/test_error_integration.py` | Integration | P0 |
| `tests/test_human_in_loop.py` | Unit + Bugfix | **P0** |
| `tests/test_agent_protocol.py` | Integration | P0 |
| `tests/test_structured_catch.py` | Unit | P1 |
| `tests/test_retry_handler.py` | Unit | P1 |
| `tests/test_retry_integration.py` | Integration | P1 |
| `tests/test_no_swallowed_exceptions.py` | Integration | P1 |
| `tests/test_compression.py` | Unit | P1 |
| `tests/test_long_term.py` | Unit | P1 |
| `tests/test_agent_routing.py` | Unit | P1 |
| `tests/test_agent_lifecycle.py` | Unit | P2 |
| `tests/test_tool_results.py` | Unit | P2 |
| `tests/test_idempotency_key.py` | Unit | P2 |
| `tests/test_supervisor.py` | Unit | P2 |
| `tests/test_api_error_format.py` | E2E | P3 |

### 6. 实施顺序
- 严格按阶段顺序执行：P1 → P2 → ... → P8
- P0（HITL Bug T15）归入 P2.4（不提前）

---

## P1 — 基础协议层

### P1.1 创建 `schemas/agent_protocol.py`

#### 目标
提取 `agent.py:34-50` 已有 `AgentError` 为独立 Schema，所有模块共用。

#### 现状（代码审查修正）
`agent.py:34-62` 定义了简化版 `AgentError`（6字段）和 `ErrorType`（3 variant），但：
- 仅在 `agent.py` 内部使用，其他模块无结构化错误格式
- 缺少 `ErrorLevel` 严重级别
- 缺少 `retry_after_ms`、`fallback_action`、`timestamp` 等字段
- 缺少 `AgentInput`/`AgentOutput` TypedDict
- 缺少 `StructuredAgentError` 异常类

#### 目标状态
```
src/agent/schemas/
├── __init__.py          # 导出全部
└── agent_protocol.py    # ErrorEnvelope, AgentInput, AgentOutput, StructuredAgentError
```

#### 实现任务

**T1. 创建 `src/agent/schemas/agent_protocol.py`**

```python
from dataclasses import dataclass, field
from typing import TypedDict, Literal, Optional, Any
from enum import Enum
import time
import logging
import uuid

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    RECOVERABLE = "recoverable"    # LLM 429、工具超时、网络抖动
    FATAL = "fatal"                # 参数非法、预算耗尽
    SYSTEM = "system"               # 内存 OOM、磁盘满、依赖宕机
    VALIDATION = "validation"       # 格式不合规、越权请求


class ErrorLevel(Enum):
    """错误严重级别，用于快速判断处理策略"""
    LOW = 0      # 警告，继续执行
    MEDIUM = 1   # 重试或降级
    HIGH = 2     # 立即终止
    CRITICAL = 3 # 触发熔断 + 人工介入


@dataclass
class ErrorEnvelope:
    """标准错误信封 - 设计规范参考: agent-flow-design.md 3.1 节"""
    error_code: str
    error_type: ErrorType
    message: str
    retryable: bool = True
    retry_after_ms: int = 0
    trace_id: str = ""
    context_snapshot: dict = field(default_factory=dict)
    fallback_action: str = "none"          # skip_and_notify | retry_later | degrade | abort
    error_level: ErrorLevel = ErrorLevel.MEDIUM
    timestamp: str = ""
    tool_name: str = ""
    step: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        error_code: str = "INTERNAL_ERROR",
        error_type: ErrorType = ErrorType.RECOVERABLE,
        retryable: bool = True,
        trace_id: str = "",
        context: dict = None,
        tool_name: str = "",
        step: int = 0,
    ) -> "ErrorEnvelope":
        """从任意异常构造 ErrorEnvelope"""
        # ERROR_CODES 在本文件底部定义，不需要从 retry_handler 导入
        # 尝试通过错误码字典查找分类
        error_key = type(exc).__name__
        if hasattr(exc, "message"):
            error_key = str(exc.message)
        code_info = ERROR_CODES.get(error_key, ERROR_CODES.get(error_code, {}))
        return cls(
            error_code=code_info.get("error_code", error_code),
            error_type=code_info.get("error_type", error_type),
            message=str(exc),
            retryable=code_info.get("retryable", retryable),
            retry_after_ms=code_info.get("retry_after_ms", 2000),
            trace_id=trace_id or _get_or_create_trace_id(),
            context_snapshot=context or {},
            error_level=code_info.get("level", ErrorLevel.MEDIUM),
            tool_name=tool_name,
            step=step,
        )

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "error_type": self.error_type.value,
            "message": self.message,
            "retryable": self.retryable,
            "retry_after_ms": self.retry_after_ms,
            "trace_id": self.trace_id,
            "context_snapshot": self.context_snapshot,
            "fallback_action": self.fallback_action,
            "error_level": self.error_level.value,
            "timestamp": self.timestamp,
            "tool_name": self.tool_name,
            "step": self.step,
        }

    def to_jsonrpc(self) -> dict:
        """JSON-RPC 2.0 错误格式"""
        code_map = {
            ErrorType.RECOVERABLE: -32000,
            ErrorType.FATAL: -32001,
            ErrorType.SYSTEM: -32002,
            ErrorType.VALIDATION: -32003,
        }
        return {
            "code": code_map.get(self.error_type, -32000),
            "message": f"[{self.error_code}] {self.message}",
            "data": self.to_dict(),
        }

    def is_critical(self) -> bool:
        return self.error_level in (ErrorLevel.HIGH, ErrorLevel.CRITICAL)

    def should_retry(self) -> bool:
        return self.retryable and not self.is_critical()


class AgentInput(TypedDict):
    """结构化 Agent 输入"""
    trace_id: str
    task: str
    tools: list[dict]         # [{name, description, schema}]
    config: dict              # {max_steps, max_tokens, temperature, timeout}
    context: dict             # {thread_id, sop_name, user_id, ...}
    session_id: Optional[str]


class AgentOutput(TypedDict):
    """结构化 Agent 输出"""
    status: Literal["success", "failed", "timeout", "partial"]
    result: Any
    trace_log: list[dict]     # [{step, action, observation, timestamp}]
    token_usage: dict        # {prompt_tokens, completion_tokens, total, budget}
    cost_usd: float
    error: Optional[dict]     # ErrorEnvelope.to_dict()
    trace_id: str
    steps_executed: int
    iterations: int
    ended_at: str


class StructuredAgentError(Exception):
    """结构化 Agent 异常 - 用于 raise"""
    def __init__(
        self,
        error_code: str = "INTERNAL_ERROR",
        error_type: ErrorType = ErrorType.RECOVERABLE,
        message: str = "",
        retryable: bool = True,
        trace_id: str = "",
        context: dict = None,
        fallback_action: str = "none",
        error_level: ErrorLevel = ErrorLevel.MEDIUM,
    ):
        self.envelope = ErrorEnvelope(
            error_code=error_code,
            error_type=error_type,
            message=message,
            retryable=retryable,
            trace_id=trace_id,
            context_snapshot=context or {},
            fallback_action=fallback_action,
            error_level=error_level,
        )
        super().__init__(message)

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        trace_id: str = "",
        context: dict = None,
        tool_name: str = "",
        step: int = 0,
    ) -> "StructuredAgentError":
        """从异常构造"""
        env = ErrorEnvelope.from_exception(
            exc,
            trace_id=trace_id,
            context=context,
            tool_name=tool_name,
            step=step,
        )
        return cls(
            error_code=env.error_code,
            error_type=env.error_type,
            message=str(exc),
            retryable=env.retryable,
            trace_id=trace_id,
            context=context,
            fallback_action=env.fallback_action,
            error_level=env.error_level,
        )

    def to_envelope(self) -> ErrorEnvelope:
        return self.envelope


def _get_or_create_trace_id() -> str:
    try:
        from ..trace_context import get_trace_id, set_trace_id, generate_trace_id
        tid = get_trace_id()
        if not tid:
            tid = generate_trace_id()
            set_trace_id(tid)
        return tid
    except Exception:
        return generate_trace_id()


# 错误码定义表 - 设计规范参考: agent-flow-design.md 表3
ERROR_CODES: dict[str, dict] = {
    # LLM 相关
    "LLM_TIMEOUT": {
        "error_code": "LLM_TIMEOUT",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 2000,
        "level": ErrorLevel.MEDIUM,
    },
    "LLM_RATE_LIMIT": {
        "error_code": "LLM_RATE_LIMIT",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 5000,
        "level": ErrorLevel.MEDIUM,
    },
    "LLM_INVALID_RESPONSE": {
        "error_code": "LLM_INVALID_RESPONSE",
        "error_type": ErrorType.FATAL,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    "LLM_API_ERROR": {
        "error_code": "LLM_API_ERROR",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 2000,
        "level": ErrorLevel.MEDIUM,
    },
    # 工具相关
    "TOOL_NOT_FOUND": {
        "error_code": "TOOL_NOT_FOUND",
        "error_type": ErrorType.FATAL,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    "TOOL_EXEC_ERROR": {
        "error_code": "TOOL_EXEC_ERROR",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 1000,
        "level": ErrorLevel.MEDIUM,
    },
    "TOOL_EXEC_TIMEOUT": {
        "error_code": "TOOL_EXEC_TIMEOUT",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 3000,
        "level": ErrorLevel.MEDIUM,
    },
    "TOOL_ARGUMENT_ERROR": {
        "error_code": "TOOL_ARGUMENT_ERROR",
        "error_type": ErrorType.FATAL,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    "TOOL_PERMISSION_DENIED": {
        "error_code": "TOOL_PERMISSION_DENIED",
        "error_type": ErrorType.FATAL,
        "retryable": False,
        "level": ErrorLevel.CRITICAL,
    },
    "TOOL_IDEMPOTENCY_CONFLICT": {
        "error_code": "TOOL_IDEMPOTENCY_CONFLICT",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 1000,
        "level": ErrorLevel.MEDIUM,
    },
    # 预算相关
    "BUDGET_EXHAUSTED": {
        "error_code": "BUDGET_EXHAUSTED",
        "error_type": ErrorType.FATAL,
        "retryable": False,
        "level": ErrorLevel.CRITICAL,
    },
    "MAX_STEPS_EXCEEDED": {
        "error_code": "MAX_STEPS_EXCEEDED",
        "error_type": ErrorType.FATAL,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    "MAX_ITERATIONS_EXCEEDED": {
        "error_code": "MAX_ITERATIONS_EXCEEDED",
        "error_type": ErrorType.FATAL,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    # Supervisor
    "SUPERVISOR_BUILD_ERROR": {
        "error_code": "SUPERVISOR_BUILD_ERROR",
        "error_type": ErrorType.FATAL,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    "SUPERVISOR_AGENT_ERROR": {
        "error_code": "SUPERVISOR_AGENT_ERROR",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 3000,
        "level": ErrorLevel.MEDIUM,
    },
    # 系统
    "INTERNAL_ERROR": {
        "error_code": "INTERNAL_ERROR",
        "error_type": ErrorType.SYSTEM,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    "CONTEXT_INIT_ERROR": {
        "error_code": "CONTEXT_INIT_ERROR",
        "error_type": ErrorType.SYSTEM,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    "CHECKPOINT_ERROR": {
        "error_code": "CHECKPOINT_ERROR",
        "error_type": ErrorType.SYSTEM,
        "retryable": True,
        "retry_after_ms": 1000,
        "level": ErrorLevel.HIGH,
    },
    # LLM 增强相关
    "LLM_ENRICH_FAILED": {
        "error_code": "LLM_ENRICH_FAILED",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 2000,
        "level": ErrorLevel.LOW,
    },
    "LLM_SUMMARIZE_FAILED": {
        "error_code": "LLM_SUMMARIZE_FAILED",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 3000,
        "level": ErrorLevel.LOW,
    },
}
```

**T2. 创建 `src/agent/schemas/__init__.py`**

```python
from .agent_protocol import (
    ErrorEnvelope,
    ErrorType,
    ErrorLevel,
    AgentInput,
    AgentOutput,
    StructuredAgentError,
    ERROR_CODES,
    _get_or_create_trace_id,
)

__all__ = [
    "ErrorEnvelope",
    "ErrorType",
    "ErrorLevel",
    "AgentInput",
    "AgentOutput",
    "StructuredAgentError",
    "ERROR_CODES",
    "_get_or_create_trace_id",
]
```

#### P1.1 测试覆盖

**`tests/test_error_envelope.py`** (新建)

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_error_envelope_creation` | 基础构造、所有字段 | Mock |
| `test_error_envelope_from_exception` | 从 Exception 构造 | Mock |
| `test_error_envelope_to_dict` | 序列化格式 | Mock |
| `test_error_envelope_to_jsonrpc` | JSON-RPC 格式 | Mock |
| `test_error_codes_lookup` | ERROR_CODES 查表 | Mock |
| `test_error_level_critical_check` | is_critical / should_retry | Mock |
| `test_structured_agent_error_raise` | 异常 raise/catch 循环 | Mock |
| `test_error_envelope_serialization_roundtrip` | dict → Envelope → dict | Mock |

**`tests/test_error_integration.py`** (新建)

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_catch_wraps_to_envelope` | `structured_catch` 装饰器 | Mock |
| `test_retryable_from_error_type` | ERROR_CODES 映射 | Mock |
| `test_trace_id_propagation` | trace_id 在错误中传播 | Mock |

#### P1.1 验收标准

- [ ] `src/agent/schemas/agent_protocol.py` 存在，导出 7 个公共符号
- [ ] `ErrorEnvelope.to_dict()` 包含 12 个字段
- [ ] `ERROR_CODES` 包含 ≥ 18 个错误码
- [ ] `StructuredAgentError.from_exception()` 可从任意 Exception 构造
- [ ] `test_error_envelope.py` 所有用例通过

---

### P1.2 统一异常处理装饰器

#### 现状
全库 66+ 处 `try/except Exception`，无统一包装。

#### 目标状态
`@structured_catch` 装饰器统一注入 ErrorEnvelope，替代所有手动 try/except。

#### 实现任务

**T3. 在 `schemas/agent_protocol.py` 中添加装饰器**

```python
from functools import wraps
from typing import Callable, TypeVar

T = TypeVar('T')

def structured_catch(
    error_code: str = "INTERNAL_ERROR",
    error_type: ErrorType = ErrorType.RECOVERABLE,
    retryable: bool = True,
    fallback_action: str = "none",
    error_level: ErrorLevel = ErrorLevel.MEDIUM,
    log_level: str = "error",
    suppress: bool = False,  # True=返回 None，False=抛出 StructuredAgentError
) -> Callable[[Callable], Callable]:
    """
    统一异常处理装饰器

    用法:
        @structured_catch(error_code="TOOL_EXEC_ERROR", error_type=ErrorType.RECOVERABLE)
        def execute_tool(input):
            ...
            return result

    设计规范参考: agent-flow-design.md 3.1 节 "禁止吞没" 规则
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T | None]:
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T | None:
            trace_id = _get_or_create_trace_id()
            context = {"func": func.__name__, "args": _safe_serialize_args(args, kwargs)}
            try:
                return func(*args, **kwargs)
            except StructuredAgentError:
                raise
            except Exception as e:
                logger.log(
                    getattr(logging, log_level.upper(), logging.ERROR),
                    f"[structured_catch] {func.__name__}: {e}"
                )
                envelope = ErrorEnvelope.from_exception(
                    e,
                    error_code=error_code,
                    error_type=error_type,
                    retryable=retryable,
                    trace_id=trace_id,
                    context=context,
                    tool_name=func.__name__,
                )
                if suppress:
                    logger.warning(
                        f"[structured_catch] {func.__name__} suppressed: {envelope.error_code}"
                    )
                    return None
                raise StructuredAgentError(
                    error_code=envelope.error_code,
                    error_type=envelope.error_type,
                    message=str(e),
                    retryable=envelope.retryable,
                    trace_id=trace_id,
                    context=context,
                    fallback_action=fallback_action,
                    error_level=error_level,
                )
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T | None:
            trace_id = _get_or_create_trace_id()
            context = {"func": func.__name__, "args": _safe_serialize_args(args, kwargs)}
            try:
                return await func(*args, **kwargs)
            except StructuredAgentError:
                raise
            except Exception as e:
                logger.log(
                    getattr(logging, log_level.upper(), logging.ERROR),
                    f"[structured_catch] {func.__name__}: {e}"
                )
                if suppress:
                    return None
                raise StructuredAgentError.from_exception(
                    e, trace_id=trace_id, context=context, tool_name=func.__name__
                )
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def _safe_serialize_args(args, kwargs) -> dict:
    """安全序列化参数（避免泄露敏感信息）"""
    try:
        safe_kwargs = {k: str(v)[:200] for k, v in kwargs.items()}
        return {"args_count": len(args), "kwargs": safe_kwargs}
    except Exception:
        return {"args_count": len(args)}
```

#### P1.2 测试覆盖

**`tests/test_structured_catch.py`** (新建)

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_sync_function_success` | 正常执行返回结果 | Mock |
| `test_sync_function_raises_structured` | 异常被包装为 StructuredAgentError | Mock |
| `test_sync_function_suppress_returns_none` | suppress=True 返回 None | Mock |
| `test_async_function_success` | async 函数正常执行 | Mock |
| `test_async_function_raises` | async 异常被包装 | Mock |
| `test_retryable_flag` | retryable=False 被正确设置 | Mock |
| `test_log_level_config` | log_level 参数控制日志级别 | Mock |

#### P1.2 验收标准

- [ ] `@structured_catch` 装饰器可应用于 sync 和 async 函数
- [ ] 异常被包装为 `StructuredAgentError`
- [ ] `suppress=True` 时不抛出异常
- [ ] 测试 `test_structured_catch.py` 所有用例通过

---

### P1.3 接入重试基础设施

#### 现状
`retry_handler.py` 定义了 `@retry_with_backoff`、`RetryableTool`、`RetryManager`，但**零处实际调用**。

#### 目标状态
重试装饰器接入所有 LLM 调用、工具调用、Supervisor 执行节点。接入前检查预算和熔断状态。

#### 架构说明（代码审查修正）

| 项目 | 原计划 | 实际现状 |
|------|--------|---------|
| `ERROR_CODES` 位置 | `retry_handler.py` 导出供 schemas 使用 | `ERROR_CODES` 定义在 `agent.py` 内部 |
| `ErrorType` | schemas 定义 | `agent.py` 定义仅有 3 个 variant |
| `AgentError` 字段数 | 12 字段 ErrorEnvelope | 当前仅 6 字段简化版 |

> ⚠️ **T4 循环依赖风险**：`retry_handler.py` 当前无任何 agent 相关导入。T4 计划从 `schemas/` 导入，但 `schemas/` 由 T1 创建。**实施顺序 T1→T2→T4 即可规避**。

#### 实现任务

**T4. 修改 `src/agent/retry_handler.py`** — 增强集成能力

> ⚠️ 前提：T1（`schemas/agent_protocol.py`）必须先完成，否则 `from src.agent.schemas import` 会 import error

```python
# 新增: 从 schemas 导入 ERROR_CODES（在 T1 完成后生效）
from src.agent.schemas import ErrorEnvelope, ErrorType, StructuredAgentError, ERROR_CODES

# 新增: 与 CircuitBreaker 集成
def retry_with_backoff(
    config: "RetryConfig" = None,
    error_codes: list[str] = None,
    check_budget: bool = True,
    budget: float = None,
    circuit_breaker=None,
    tool_name: str = "",
):
    """
    增强版重试装饰器

    新增参数:
        error_codes: 指定哪些错误码触发重试 (None=所有可重试)
        check_budget: 重试前检查预算
        budget: 当前剩余预算 (USD)
        circuit_breaker: CircuitBreaker 实例，执行前检查
        tool_name: 工具名称 (用于错误分类)
    """
    # ... 保留原有逻辑 ...
    # 新增: 执行前检查 circuit_breaker.can_execute()
    # 新增: 重试前检查 remaining_budget > estimated_retry_cost
    # 新增: 使用 ERROR_CODES 判断 retryable


# 新增: 带预算检查的重试包装
def retry_with_budget(
    max_retries: int = 2,
    estimated_retry_cost: float = 0.001,
    circuit_breaker=None,
):
    """
    重试前校验 remaining_budget > estimated_retry_cost

    设计规范参考: agent-flow-design.md 2.3 节 "重试必须消耗预算" 规则
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 从 kwargs 或闭包获取 budget
            remaining = kwargs.get("_remaining_budget")
            if remaining is not None and remaining < estimated_retry_cost:
                raise StructuredAgentError(
                    error_code="BUDGET_EXHAUSTED",
                    error_type=ErrorType.FATAL,
                    message=f"预算不足 ({remaining} < {estimated_retry_cost})",
                    retryable=False,
                    error_level=ErrorLevel.CRITICAL,
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

**T5. 在 `src/agent/agent.py` 中应用重试装饰器**

```python
# agent.py 顶部添加
from src.agent.schemas import (
    ErrorEnvelope, ErrorType, StructuredAgentError,
    _get_or_create_trace_id,
)
from src.agent.retry_handler import (
    retry_with_backoff,
    LLMRetryConfig,
    ToolRetryConfig,
    get_rate_limiter,
    get_tool_breakers,
)
from src.agent.rate_limiter import CircuitBreaker

# _node_think 方法头部添加 (约 L297-309 区域)
class Agent:
    @retry_with_backoff(
        config=LLMRetryConfig(),
        check_budget=True,
        circuit_breaker=None,  # LLM 熔断器
        tool_name="llm",
    )
    def _node_think(self, state: AgentState) -> AgentState:
        # 原有逻辑...

    # _node_execute 方法头部添加 (约 L385 区域)
    def _node_execute(self, state: AgentState) -> AgentState:
        for call in tool_calls:
            tool_name = _msg_get(call, "name")
            breaker = get_tool_breakers().get(tool_name)
            if breaker and not breaker.can_execute():
                # 熔断中的工具，跳过并记录警告
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": f"【熔断中】工具 {tool_name} 当前不可用",
                    "status": "breaker_open",
                })
                continue
            # 原有工具执行逻辑保持不变...
```

#### P1.3 测试覆盖

**`tests/test_retry_handler.py`** (新建)

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_retry_succeeds_on_third_attempt` | 3次重试后成功 | Mock |
| `test_retry_respects_max_retries` | 达到上限后抛出 | Mock |
| `test_retry_respects_budget` | 预算不足时不重试 | Mock |
| `test_retry_with_circuit_breaker` | 熔断开启时跳过执行 | Mock |
| `test_retry_error_codes_filter` | 只对指定错误码重试 | Mock |
| `test_retry_manager_tracks_stats` | RetryManager 统计 | Mock |
| `test_llm_retry_config` | LLMRetryConfig 参数 | Mock |
| `test_tool_retry_config` | ToolRetryConfig 参数 | Mock |

**`tests/test_retry_integration.py`** (新建)

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_agent_node_think_retries_on_llm_error` | _node_think LLM 错误重试 | Mock |
| `test_agent_node_execute_skips_when_breaker_open` | 熔断开启时跳过工具 | Mock |
| `test_agent_retries_with_budget_check` | 预算不足不重试 | Mock |

#### P1.3 验收标准

- [ ] `_node_think` 被 `@retry_with_backoff(LLMRetryConfig())` 包装
- [ ] `_node_execute` 工具执行前检查 `get_tool_breakers()[tool_name].can_execute()`
- [ ] 重试前检查 `remaining_budget > estimated_retry_cost`
- [ ] `test_retry_handler.py` 所有用例通过
- [ ] `test_retry_integration.py` 所有用例通过

---

### P1.4 消除吞没异常

#### 现状（代码审查修正后）

| 文件 | 行 | 代码 | 问题 | 实际状态 |
|------|----|------|------|---------|
| `compression.py` | 199 | `except Exception: pass` | LLM 提取失败静默吞没 | ❌ 已修复 - 实为 `logger.warning()` + 隐式 return |
| `tools/__init__.py` | 42 | `except: pass` | 临时文件清理失败静默 | ⚠️ finally 块，可接受 |
| `tools/__init__.py` | 213 | `except: pass` | 文件读失败静默 | 🔴 **真实问题** - 搜索失败用户无感知 |
| `orchestrator_checkpoint.py` | 141 | `except Exception: continue` | JSON 解析失败静默 | 🔴 **真实问题** - 损坏的 JSON 被静默跳过 |

> 📌 代码审查结论：全库仅 2 处真正需要修复的吞没异常：`tools/__init__.py:213` 和 `orchestrator_checkpoint.py:141`

#### 实现任务

**T6. 修复 `src/agent/context/compression.py`**

```python
# L199 区域 (约 L157-200 _enrich_turns_with_llm)
# 原始:
# except Exception as e:
#     logger.warning(f"[LLM Enrich] Failed: {e}, using empty fields")
#     return  # ← 静默吞没

# 修改为:
from src.agent.schemas import structured_catch, ErrorEnvelope, ErrorType

class ContextCompressor:
    @structured_catch(
        error_code="LLM_ENRICH_FAILED",
        error_type=ErrorType.RECOVERABLE,
        error_level=ErrorLevel.LOW,
        suppress=True,  # LLM 提取失败不影响主流程，保留空字段
        log_level="warning",
    )
    def _enrich_turns_with_llm(self, turns: list[CompressedTurn]) -> None:
        """LLM 提取 key_facts 和 unresolved"""
        # ... 原有逻辑 ...

    # L275 区域 (_llm_summarize_turns)
    # 原始 except -> 改为 raise StructuredAgentError (失败应传播)
    @structured_catch(
        error_code="LLM_SUMMARIZE_FAILED",
        error_type=ErrorType.RECOVERABLE,
        error_level=ErrorLevel.LOW,
        suppress=False,  # 摘要失败应传播
    )
    def _llm_summarize_turns(self, turns: list[CompressedTurn]) -> str:
        # ... 原有逻辑 ...
```

**T7. 修复 `src/agent/tools/__init__.py`**

```python
# L213 区域 (search_files 内层循环)
# 原始: for file_path in files: try: ... except: pass
# 修改为:
for file_path in files:
    try:
        # ...
    except Exception as e:
        errors.append(f"读取失败 {file_path}: {e}")
        continue  # 跳过失败文件，收集错误

# L40-43 区域 (execute_code finally 块)
# 原始: except: pass
# 修改为:
finally:
    try:
        os.unlink(temp_path)
    except Exception as e:
        logger.warning(f"[execute_code] 临时文件清理失败: {temp_path}, {e}")
```

**T8. 修复 `src/agent/orchestrator_checkpoint.py`**

```python
# L141 区域 (_get_last_turn_count)
# 原始: except Exception: continue
# 修改为:
from src.agent.schemas import structured_catch

@structured_catch(
    error_code="CHECKPOINT_ERROR",
    error_type=ErrorType.SYSTEM,
    error_level=ErrorLevel.MEDIUM,
    suppress=True,
    log_level="warning",
)
def _get_last_turn_count(self, session_file: Path) -> int:
    # ... 原有逻辑 ...
```

#### P1.4 测试覆盖

复用 `test_context_integration.py` 和 `test_orchestrator_checkpoint.py`，新增:

**`tests/test_no_swallowed_exceptions.py`** (新建)

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_compression_enrich_fails_logs_not_swallows` | LLM enrich 失败时 logger.warning 而非 pass | Mock |
| `test_tools_file_read_error_collected` | 文件读失败被收集到 errors 列表 | Mock |
| `test_tools_temp_file_cleanup_warning` | 临时文件清理失败 logger.warning | Mock |
| `test_checkpoint_parse_error_logs_warning` | JSON 解析失败 logger.warning | Mock |

#### P1.4 验收标准

- [ ] `grep -r "except: pass" src/agent/` 返回 0 结果
- [ ] `grep -r "except Exception: pass" src/agent/` 返回 0 结果
- [ ] `grep -r "except Exception: continue" src/agent/` 返回 0 结果
- [ ] `test_no_swallowed_exceptions.py` 所有用例通过

---

## P2 — Agent 层对齐

### P2.1 结构化 AgentInput / AgentOutput

#### 现状
`agent.py:run()` L483-515 接受 `input_text: str`，返回 `{"status": "success", "result": result}`。

#### 目标状态
`run()` 同时接受 `AgentInput` (TypedDict) 和 原始字符串（向后兼容），返回 `AgentOutput` (TypedDict)。

#### 实现任务

**T9. 重构 `src/agent/agent.py:run()`**

```python
# agent.py 约 L483-515

def run(
    self,
    input_text: str = None,
    thread_id: str = "default",
    sop_name: str = None,
    input_obj: AgentInput = None,  # 新增: 结构化输入
) -> AgentOutput:
    """
    运行 Agent

    支持两种调用方式:
        1. run("你好")                    # 向后兼容
        2. run(input_obj={"trace_id": ..., "task": ..., ...})  # 结构化
    """
    import time
    start_time = time.time()
    trace_id = _get_or_create_trace_id()
    trace_log = []
    step_count = 0

    # 解析输入
    if input_obj is not None:
        task = input_obj.get("task", "")
        config = input_obj.get("config", {})
        max_steps = config.get("max_steps", 50)
        context = input_obj.get("context", {})
    else:
        task = input_text or ""
        max_steps = 50
        context = {}

    # 构建初始状态
    initial_state = create_initial_state(thread_id)
    new_user_msg = {"role": "user", "content": task}
    initial_state["messages"] = [new_user_msg]
    if sop_name:
        initial_state["sop_name"] = sop_name

    # 从 checkpointer 恢复已有消息
    namespaced_id = make_thread_id(
        tenant_id=os.getenv("AGENT_TENANT_ID", "default"),
        org_id=os.getenv("AGENT_ORG_ID", "default"),
        user_id=os.getenv("AGENT_USER_ID", "default"),
        session_id=thread_id,
    )
    config = {"configurable": {"thread_id": namespaced_id}}
    checkpoint = self.checkpointer.get(config)
    if checkpoint and checkpoint.get("channel_values", {}).get("messages"):
        existing = checkpoint["channel_values"]["messages"]
        existing = _deduplicate_messages(existing)
        initial_state["messages"] = existing + [new_user_msg]
        trace_log.append({
            "step": len(trace_log),
            "action": "resume",
            "observation": f"恢复 {len(existing)} 条消息",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    try:
        if not self._graph:
            self._build_graph()

        result = self._graph.invoke(initial_state, config)
        elapsed = time.time() - start_time

        # 提取最终消息和指标
        messages = result.get("messages", [])
        metrics = self.get_metrics()
        ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")

        return AgentOutput(
            status="success",
            result={"messages": messages},
            trace_log=trace_log,
            token_usage=metrics,
            cost_usd=metrics.get("total_cost_usd", 0),
            error=None,
            trace_id=trace_id,
            steps_executed=metrics.get("compressions", 0),
            iterations=len(messages),
            ended_at=ended_at,
        )
    except StructuredAgentError as e:
        return self._build_error_output(e, trace_log, start_time, trace_id)
    except Exception as e:
        env = ErrorEnvelope.from_exception(
            e,
            error_code="INTERNAL_ERROR",
            trace_id=trace_id,
            context={"input": task[:200]},
        )
        raise StructuredAgentError(
            error_code=env.error_code,
            error_type=env.error_type,
            message=str(e),
            retryable=False,
            trace_id=trace_id,
            context=context,
        )

def _build_error_output(
    self, error: StructuredAgentError, trace_log: list, start_time: float, trace_id: str
) -> AgentOutput:
    env = error.to_envelope()
    return AgentOutput(
        status="failed",
        result=None,
        trace_log=trace_log,
        token_usage={},
        cost_usd=0.0,
        error=env.to_dict(),
        trace_id=trace_id,
        steps_executed=0,
        iterations=0,
        ended_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
```

**T10. 重构 `src/agent/state.py`** — 添加缺少的字段

```python
# state.py AgentState 添加新字段
class AgentState(TypedDict):
    messages: Annotated[list, smart_message_reducer]
    thread_id: str
    task_status: Literal["pending", "in_progress", "completed", "failed", "paused", "aborted"]  # 新增 paused/aborted
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
    step_count: int = 0                  # 新增: 步数计数器
    current_action: str = ""            # 新增: 当前执行动作
    last_error: dict | None              # 新增: ErrorEnvelope.to_dict()
    trace_id: str = ""                    # 新增: 追踪 ID
```

#### P2.1 测试覆盖

**`tests/test_agent_protocol.py`** (新建)

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_run_returns_agent_output_structure` | 返回值包含 AgentOutput 所有字段 | Mock |
| `test_run_backward_compatible` | 传入字符串仍可正常工作 | Mock |
| `test_run_with_input_obj` | 传入 AgentInput 结构化对象 | Mock |
| `test_run_error_includes_envelope` | 失败时 error 字段为 ErrorEnvelope | Mock |
| `test_stream_returns_agent_output` | stream() 也返回 AgentOutput | Mock |
| `test_run_trace_log_populated` | trace_log 非空 | Mock |
| `test_run_with_real_api` | Real API 验证结构 | **Real** |

#### P2.1 验收标准

- [ ] `run()` 返回类型为 `AgentOutput`
- [ ] `AgentOutput` 包含 12 个必需字段
- [ ] 字符串输入（向后兼容）正常工作
- [ ] 失败时 `error` 字段包含 `ErrorEnvelope.to_dict()`
- [ ] `test_agent_protocol.py` 所有用例通过

---

### P2.2 添加 max_steps 限制

#### 现状（代码审查修正）
`config.py` 无 `max_steps` 配置。`_should_continue` 已实现 `MAX_ITERATIONS=50` 硬限制，但：
- 无配置项，需硬编码修改
- `step_count` 字段已在 `agent.py` 实现（每次 think 后递增），但 `_should_continue` 尚未使用
- 无 `max_steps` 配置与 `max_iterations` 配置分离

#### 目标状态
`config.py` 添加 `max_steps: int = 50`。`_should_continue` 同时检查 `step_count <= max_steps`。

#### 实现任务

**T11. 修改 `src/agent/config.py`**

> ⚠️ 注意：`iteration_count` 已在 `_node_think` 中递增，只需在 `config.py` 中暴露配置项即可

```python
# config.py ShortTermConfig 中添加
class ShortTermConfig(BaseSettings):
    max_tokens: int = 128000
    trigger_threshold: float = 0.7
    keep_recent: int = 5
    max_steps: int = 50              # 新增: 最大步数 (已实现硬编码，迁移到配置)
    max_iterations: int = 50          # 新增: 最大迭代 (已实现硬编码，迁移到配置)
    hot_zone_size: int = 5
```

**T12. 修改 `src/agent/agent.py:_should_continue`**

```python
# agent.py _should_continue 已实现 MAX_ITERATIONS=50，需改为读取配置
MAX_ITERATIONS = 50  # 移除硬编码，改为 self.config.short_term.max_iterations
```
    task_status = state.get("task_status")
    compression_count = state.get("compression_count", 0)
    step_count = state.get("step_count", 0)
    max_steps = self.config.short_term.max_steps
    max_iterations = self.config.short_term.max_iterations

    # 硬限制检查
    if step_count >= max_steps:
        logger.info(f"[Route] 硬限制: step_count={step_count} >= max_steps={max_steps}")
        return END
    if compression_count >= 5:
        logger.info(f"[Route] 压缩次数超限: {compression_count} >= 5")
        return END
    if task_status != "in_progress":
        logger.info(f"[Route] 任务非进行中: {task_status}")
        return END

    return "think"
```

**T13. 修改 `src/agent/agent.py` — 步数递增**

```python
# _node_think 或 _node_compress 中递增 step_count
def _node_think(self, state: AgentState) -> AgentState:
    # ... 原有逻辑 ...
    step_count = state.get("step_count", 0) + 1
    return {
        "messages": result_msg,
        "token_usage": token_update["token_usage"],
        "step_count": step_count,  # 新增
        **token_update,
    }
```

#### P2.2 测试覆盖

**`tests/test_agent_routing.py`** 扩展

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_routes_to_end_when_max_steps` | step_count >= max_steps → end | Mock |
| `test_routes_to_end_when_max_iterations` | 迭代超限 → end | Mock |
| `test_step_count_increments` | step_count 每次递增 | Mock |
| `test_config_max_steps_default` | 默认 max_steps = 50 | Mock |
| `test_config_max_steps_custom` | 自定义 max_steps 生效 | Mock |

#### P2.2 验收标准

- [ ] `config.py` ShortTermConfig 包含 `max_steps` 和 `max_iterations`
- [ ] `_should_continue` 检查 `step_count >= max_steps`
- [ ] 步数超限时返回 END
- [ ] `test_agent_routing.py` 新增 5 个用例通过

---

### P2.3 添加 pause / resume / abort 接口

#### 现状
`supervisor.py` 有 `interrupt()` / `resume()`，但 `Agent` 类没有。

#### 实现任务

**T14. 在 `src/agent/agent.py` 中添加生命周期管理**

```python
class Agent:
    def pause(self, thread_id: str = "default") -> dict:
        """暂停 Agent 执行"""
        namespaced_id = make_thread_id(session_id=thread_id)
        config = {"configurable": {"thread_id": namespaced_id}}
        checkpoint = self.checkpointer.get(config)
        if checkpoint:
            channel_values = checkpoint.get("channel_values", {})
            channel_values["task_status"] = "paused"
            self.checkpointer.put(config, channel_values)
            return {"status": "success", "action": "paused", "thread_id": thread_id}
        return {"status": "error", "message": "无checkpoint可暂停"}

    def abort(self, thread_id: str = "default") -> dict:
        """终止 Agent 执行"""
        namespaced_id = make_thread_id(session_id=thread_id)
        config = {"configurable": {"thread_id": namespaced_id}}
        checkpoint = self.checkpointer.get(config)
        if checkpoint:
            channel_values = checkpoint.get("channel_values", {})
            channel_values["task_status"] = "aborted"
            self.checkpointer.put(config, channel_values)
            return {"status": "success", "action": "aborted", "thread_id": thread_id}
        return {"status": "error", "message": "无checkpoint可终止"}

    def resume(self, thread_id: str = "default") -> dict:
        """恢复暂停的 Agent"""
        namespaced_id = make_thread_id(session_id=thread_id)
        config = {"configurable": {"thread_id": namespaced_id}}
        checkpoint = self.checkpointer.get(config)
        if checkpoint:
            channel_values = checkpoint.get("channel_values", {})
            status = channel_values.get("task_status", "")
            if status == "paused":
                channel_values["task_status"] = "in_progress"
                self.checkpointer.put(config, channel_values)
                return {"status": "success", "action": "resumed", "thread_id": thread_id}
            return {"status": "error", "message": f"当前状态不可恢复: {status}"}
        return {"status": "error", "message": "无checkpoint可恢复"}
```

#### P2.3 测试覆盖

**`tests/test_agent_lifecycle.py`** (新建)

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_pause_sets_status_to_paused` | pause() 设置状态 | Mock |
| `test_abort_sets_status_to_aborted` | abort() 设置状态 | Mock |
| `test_resume_from_paused` | 从 paused 恢复 | Mock |
| `test_resume_from_non_paused_fails` | 非 paused 状态不可恢复 | Mock |
| `test_pause_nonexistent_thread` | 无效 thread_id 返回 error | Mock |

#### P2.3 验收标准

- [ ] `Agent.pause()` 方法存在且可调用
- [ ] `Agent.abort()` 方法存在且可调用
- [ ] `Agent.resume()` 可从 paused 状态恢复
- [ ] `test_agent_lifecycle.py` 所有用例通过

---

### P2.4 修复 HITL 审批逻辑 Bug

#### 现状 — **🔴 P0 严重 Bug（阻塞所有人工审批）**
`human_in_loop.py:106-111` 中 `asyncio.Event.wait()` 返回 `None`，导致所有审批表现为"已拒绝"。

> ⚠️ **实现现状**：`agent.py` 已添加 `human_review` 节点（L273-289），但底层 `request_approval()` 方法的 bug 未修复，审批仍返回 `None`。

```python
# human_in_loop.py L106-115 (原始错误)
approved = await asyncio.wait_for(
    self._approval_events[request_id].wait(), timeout=timeout
)
return approved  # ← 永远是 None

# 调用方 orchestrator_v2.py L323-328 (原始)
approved = await asyncio.to_thread(request_step_approval)
if not approved:  # ← None 是 falsy，误判为拒绝
    step.status = "rejected"
```

#### 实现任务

**T15. 修复 `src/agent/human_in_loop.py`**

```python
# human_in_loop.py 约 L99-115

async def request_approval(
    self,
    request_id: str,
    approval_type: ApprovalType,
    description: str,
    details: dict = None,
    timeout: int = 300,
) -> bool:
    """
    请求审批

    Returns:
        True  - 已批准
        False - 已拒绝或超时
    """
    if not self._is_critical_operation(approval_type):
        return True  # 非关键操作自动放行

    if request_id in self._pending_approvals:
        return False  # 已存在待审批

    request = ApprovalRequest(
        request_id=request_id,
        approval_type=approval_type,
        description=description,
        details=details or {},
        status=ApprovalStatus.PENDING,
        requested_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=datetime.now().isoformat(),
    )
    self._pending_approvals[request_id] = request
    self._approval_events[request_id] = asyncio.Event()

    # 执行回调
    for callback in self._callbacks:
        try:
            callback(request)
        except Exception as e:
            logger.warning(f"[HITL] Callback failed: {e}")

    try:
        # ✅ 修复: 等待 event.set() 后检查 request.status
        event = self._approval_events[request_id]
        await asyncio.wait_for(event.wait(), timeout=timeout)
        # event 已触发，检查实际审批状态
        return request.status == ApprovalStatus.APPROVED
    except asyncio.TimeoutError:
        request.status = ApprovalStatus.EXPIRED
        return False
    finally:
        # 清理
        self._pending_approvals.pop(request_id, None)
        self._approval_events.pop(request_id, None)


def approve(self, request_id: str, approved_by: str = "system", comment: str = "") -> bool:
    """批准请求"""
    request = self._pending_approvals.get(request_id)
    if not request:
        logger.warning(f"[HITL] approve: 未找到请求 {request_id}")
        return False
    request.status = ApprovalStatus.APPROVED
    request.approved_by = approved_by
    request.comment = comment
    # ✅ 修复: event.set() 后 request.status 已被设置为 APPROVED
    self._approval_events[request_id].set()
    return True


def reject(self, request_id: str, rejected_by: str = "system", comment: str = "") -> bool:
    """拒绝请求"""
    request = self._pending_approvals.get(request_id)
    if not request:
        logger.warning(f"[HITL] reject: 未找到请求 {request_id}")
        return False
    request.status = ApprovalStatus.REJECTED
    request.rejected_by = rejected_by
    request.comment = comment
    self._approval_events[request_id].set()
    return True
```

**T16. 修复 `src/agent/orchestrator_v2.py`** — 审批结果处理

```python
# orchestrator_v2.py 约 L323-328

# 原始错误:
# approved = await asyncio.to_thread(request_step_approval)
# if not approved:
#     step.status = "rejected"
#     return

# 修改为:
approved = await asyncio.to_thread(request_step_approval)
if approved:
    step.status = "waiting_approval"
else:
    # approved == False 意味着拒绝或超时
    step.status = "rejected"
    step.error = "审批被拒绝或超时"
```

#### P2.4 测试覆盖

**`tests/test_human_in_loop.py`** 扩展

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_approval_returns_true_on_approve` | approve() 后 request_approval() 返回 True | Mock |
| `test_approval_returns_false_on_reject` | reject() 后 request_approval() 返回 False | Mock |
| `test_approval_returns_false_on_timeout` | 超时后 request_approval() 返回 False | Mock |
| `test_auto_approve_non_critical` | 非关键操作自动放行 | Mock |
| `test_request_approval_concurrent_safety` | 并发安全 | Mock |
| `test_approval_status_reflects_actual_decision` | 状态反映真实决策而非 None | Mock |

#### P2.4 验收标准

- [ ] `human_in_loop.py` 中无 `return approved` 模式
- [ ] `request_approval()` 返回布尔值 True/False，无 None
- [ ] `approve()` 后 `request_approval()` 正确返回 True
- [ ] `reject()` 后 `request_approval()` 正确返回 False
- [ ] `test_human_in_loop.py` 所有用例通过

---

## P3 — 上下文系统对齐

### P3.1 Compression 结构化错误

#### 现状
`CompressionResult` dataclass 存在（6字段），但缺少 `errors: list[ErrorEnvelope]` 和 `warnings: list[str]` 字段。压缩失败时无结构化错误返回。

#### 实现任务

**T17. 重构 `src/agent/context/compression.py`** — CompressionResult 结构化

```python
# compression.py 约 L58-67 CompressionResult

from dataclasses import dataclass, field
from typing import Optional, Callable
from src.agent.schemas import ErrorEnvelope, ErrorType

@dataclass
class CompressionResult:
    """压缩结果 - 设计规范参考: context_design.md 4.1 节"""
    compressed_messages: list
    compressed_turns: list["CompressedTurn"]
    original_count: int
    compressed_count: int
    compression_ratio: float
    token_saved: int
    errors: list[ErrorEnvelope] = field(default_factory=list)  # 新增: 错误列表
    warnings: list[str] = field(default_factory=list)         # 新增: 警告列表

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


class ContextCompressor:
    def compress(self, messages: list) -> CompressionResult:
        """执行压缩，返回结构化结果"""
        errors = []
        warnings = []

        if not self.should_compress(messages):
            return CompressionResult(
                compressed_messages=messages,
                compressed_turns=[],
                original_count=len(messages),
                compressed_count=len(messages),
                compression_ratio=1.0,
                token_saved=0,
            )

        try:
            # ... 原有压缩逻辑 ...
            compressed = self._do_compress(messages)
        except Exception as e:
            from src.agent.schemas import ErrorEnvelope, StructuredAgentError
            env = ErrorEnvelope.from_exception(e, error_code="COMPRESSION_FAILED")
            errors.append(env)
            warnings.append(f"压缩失败: {e}")
            compressed = messages  # 回退到原始消息

        return CompressionResult(
            compressed_messages=compressed,
            compressed_turns=self._compressed_turns_cache,
            original_count=len(messages),
            compressed_count=len(compressed),
            compression_ratio=len(compressed) / len(messages),
            token_saved=0,
            errors=errors,
            warnings=warnings,
        )
```

#### P3.1 测试覆盖

**`tests/test_compression.py`** 扩展

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_compress_returns_compression_result` | 返回 CompressionResult | Mock |
| `test_compress_errors_are_captured` | 错误被捕获到 errors 列表 | Mock |
| `test_compress_warnings_are_captured` | 警告被捕获 | Mock |
| `test_compress_fallback_on_error` | 失败时回退到原始消息 | Mock |
| `test_enrich_fails_with_envelope` | LLM enrich 失败返回 ErrorEnvelope | Mock |

#### P3.1 验收标准

- [ ] `compress()` 返回 `CompressionResult` 而非 list
- [ ] `CompressionResult.errors` 包含 ErrorEnvelope 列表
- [ ] `CompressionResult.warnings` 包含警告列表
- [ ] 失败时回退到原始消息
- [ ] `test_compression.py` 所有新增用例通过

---

### P3.2 LongTerm 存储异常处理

#### 现状
`long_term.py:152` ChromaDB create 失败无保护。`long_term.py:263` 搜索失败返回空而非错误。

#### 实现任务

**T18. 修复 `src/agent/context/long_term.py`**

```python
# long_term.py 约 L139-156 _init_chroma
from src.agent.schemas import structured_catch, ErrorEnvelope, ErrorType

@structured_catch(
    error_code="VECTOR_STORE_INIT_ERROR",
    error_type=ErrorType.SYSTEM,
    error_level=ErrorLevel.HIGH,
    suppress=False,  # ChromaDB 初始化失败应传播
    log_level="error",
)
def _init_chroma(self):
    """初始化 ChromaDB"""
    if not self.config.vector_enabled:
        self._vector_store = None
        return

    self._chroma = chromadb.Client(ChromaSettings(
        persist_directory=self.config.chroma_persist_dir,
        anonymized_telemetry=False
    ))

    try:
        self._vector_store = self._chroma.get_collection("agent_memory")
    except Exception:
        # get 失败时才 create，create 也失败则传播
        try:
            self._vector_store = self._chroma.create_collection(
                "agent_memory",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            # 统一处理: ChromaDB 初始化完全失败
            from src.agent.schemas import StructuredAgentError
            raise StructuredAgentError(
                error_code="VECTOR_STORE_INIT_ERROR",
                error_type=ErrorType.SYSTEM,
                message=f"ChromaDB 初始化失败: {e}",
                error_level=ErrorLevel.HIGH,
            )

# long_term.py 约 L252-264 search_similar
@structured_catch(
    error_code="VECTOR_SEARCH_ERROR",
    error_type=ErrorType.RECOVERABLE,
    error_level=ErrorLevel.LOW,
    suppress=True,
    log_level="warning",
)
def search_similar(self, query: str, top_k: int = 3) -> list[str]:
    """语义搜索 - 失败时返回空列表"""
    if not self._vector_store:
        return []
    results = self._vector_store.query(
        query_texts=[query],
        n_results=top_k
    )
    return results.get("documents", [[]])[0]
```

#### P3.2 测试覆盖

**`tests/test_long_term.py`** 扩展

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_chroma_create_failure_propagates` | create 失败时抛出 StructuredAgentError | Mock |
| `test_search_similar_failure_returns_empty` | 搜索失败时返回 [] 而非抛异常 | Mock |
| `test_get_last_turn_count_json_error_logs` | JSON 解析失败时 logger.warning | Mock |

#### P3.2 验收标准

- [ ] `_init_chroma` 被 `@structured_catch` 包装
- [ ] `search_similar` 失败时 logger.warning 并返回空列表
- [ ] `_get_last_turn_count` JSON 解析失败 logger.warning
- [ ] `test_long_term.py` 所有新增用例通过

---

## P4 — 工具层对齐

### P4.1 结构化 ToolResult

#### 现状
11 个工具返回 flat string。前端无法可靠解析。

#### 实现任务

**T19. 创建 `src/agent/schemas/tool_result.py`**

```python
from dataclasses import dataclass, field
from typing import Literal, Optional
from src.agent.schemas import ErrorEnvelope, ErrorType

@dataclass
class ToolResult:
    """结构化工具结果 - 设计规范参考: agent-flow-design.md"""
    status: Literal["success", "failed", "timeout", "partial"] = "success"
    content: str = ""
    error: Optional[dict] = None     # ErrorEnvelope.to_dict()
    metadata: dict = field(default_factory=dict)  # 工具特定元数据
    idempotency_key: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "content": self.content,
            "error": self.error,
            "metadata": self.metadata,
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_error(
        cls,
        error: Exception,
        error_code: str = "TOOL_EXEC_ERROR",
        tool_name: str = "",
    ) -> "ToolResult":
        env = ErrorEnvelope.from_exception(
            error,
            error_code=error_code,
            error_type=ErrorType.RECOVERABLE,
            tool_name=tool_name,
        )
        return cls(
            status="failed",
            content=str(error),
            error=env.to_dict(),
        )
```

**T20. 修改 `src/agent/tools/__init__.py`** — 结构化返回

```python
# tools/__init__.py 顶部添加
from src.agent.schemas.tool_result import ToolResult, ToolResultSummary

def execute_code(input: dict) -> dict:
    """执行 Python 代码"""
    code = input.get("code", "")
    timeout = input.get("timeout", 30)
    idempotency_key = input.get("idempotency_key", "")

    # 原有 try/except 逻辑保持不变...
    try:
        result = subprocess.run(
            ["python", temp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return ToolResult(
            status="success",
            content=output or "代码执行完成，无输出",
            metadata={
                "exit_code": result.returncode,
                "timeout": timeout,
                "tool": "execute_code",
            },
            idempotency_key=idempotency_key,
        ).to_dict()
    except subprocess.TimeoutExpired:
        return ToolResult(
            status="timeout",
            content=f"执行超时 ({timeout}秒)",
            error=ErrorEnvelope(
                error_code="TOOL_EXEC_TIMEOUT",
                error_type=ErrorType.RECOVERABLE,
                message=f"执行超时 ({timeout}秒)",
                retryable=True,
                tool_name="execute_code",
            ).to_dict(),
        ).to_dict()
    except Exception as e:
        return ToolResult.from_error(e, "TOOL_EXEC_ERROR", "execute_code").to_dict()


def read_file(input: dict) -> dict:
    """读取文件"""
    path = input.get("path", "")
    idempotency_key = input.get("idempotency_key", "")

    try:
        # ... 原有文件读取逻辑 ...
        return ToolResult(
            status="success",
            content=content,
            metadata={
                "path": path,
                "lines": total,
                "size_bytes": os.path.getsize(path),
                "tool": "read_file",
            },
            idempotency_key=idempotency_key,
        ).to_dict()
    except FileNotFoundError:
        return ToolResult(
            status="failed",
            content=f"文件不存在: {path}",
            error=ErrorEnvelope(
                error_code="TOOL_NOT_FOUND",
                error_type=ErrorType.FATAL,
                message=f"文件不存在: {path}",
                retryable=False,
                tool_name="read_file",
            ).to_dict(),
        ).to_dict()
    # ... 其他工具同样修改 ...
```

#### P4.1 测试覆盖

**`tests/test_tool_results.py`** (新建)

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_execute_code_returns_tool_result` | execute_code 返回 ToolResult 结构 | Mock |
| `test_execute_code_timeout_returns_timeout_status` | 超时返回 status="timeout" | Mock |
| `test_execute_code_error_returns_failed_status` | 错误返回 status="failed" | Mock |
| `test_read_file_returns_metadata` | read_file 包含 metadata | Mock |
| `test_write_file_returns_tool_result` | write_file 返回 ToolResult | Mock |
| `test_data_processor_returns_metadata` | data_processor 包含 rows/cols | Mock |
| `test_tool_result_from_error_creates_envelope` | from_error 构造正确 | Mock |
| `test_tool_result_serialization_roundtrip` | dict → ToolResult → dict | Mock |

#### P4.1 验收标准

- [ ] `ToolResult` dataclass 存在
- [ ] 所有 11 个工具返回 `ToolResult.to_dict()` 格式
- [ ] 返回值包含 `status`, `content`, `error`, `metadata`
- [ ] `test_tool_results.py` 所有用例通过

---

### P4.2 幂等键支持

#### 现状
工具调用无幂等键，重复调用可能导致副作用重复。

#### 实现任务

**T21. 修改 `src/agent/agent.py:_node_execute`** — 生成幂等键

```python
# agent.py 约 L385-436 _node_execute
import uuid

def _node_execute(self, state: AgentState) -> AgentState:
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else {}
    tool_calls = _msg_get(last_msg, "tool_calls", [])
    results = []
    idempotency_keys = {}

    for call in tool_calls:
        tool_name = _msg_get(call, "name")
        tool_input = _msg_get(call, "arguments", {})
        tool_call_id = _msg_get(call, "id")

        # 生成幂等键
        idempotency_key = str(uuid.uuid4())
        idempotency_keys[tool_call_id] = idempotency_key

        # 检查缓存: 相同幂等键的结果是否已存在
        if tool_call_id in idempotency_keys:
            cached = self._get_idempotent_result(tool_call_id)
            if cached:
                results.append(cached)
                continue

        # 执行工具 (保留原有逻辑)
        for t in TOOLS:
            if t.name == tool_name:
                # 注入幂等键
                tool_input["idempotency_key"] = idempotency_key
                try:
                    result = t.invoke(tool_input)
                    # 解析 ToolResult
                    result_dict = result if isinstance(result, dict) else {"content": str(result)}
                    results.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result_dict.get("content", str(result)),
                        "status": result_dict.get("status", "success"),
                    })
                    # 缓存结果
                    self._cache_idempotent_result(tool_call_id, results[-1])
                except Exception as e:
                    # ... 错误处理 ...

    return {"messages": results}
```

#### P4.2 测试覆盖

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_tool_execution_generates_idempotency_key` | 每个工具调用生成唯一幂等键 | Mock |
| `test_duplicate_tool_call_returns_cached_result` | 相同幂等键返回缓存结果 | Mock |
| `test_idempotency_key_injected_to_tool` | 幂等键注入工具参数 | Mock |

#### P4.2 验收标准

- [ ] 每个工具调用生成唯一 `idempotency_key`
- [ ] `idempotency_key` 注入工具参数
- [ ] 相同幂等键的结果被缓存并重用
- [ ] `test_idempotency_key.py` 所有用例通过

---

## P5 — Supervisor / Orchestrator 对齐

### P5.1 Supervisor 结构化错误

#### 现状
`supervisor.py:331` 返回 `state.error = str(e)`（简单字符串），非结构化错误。

#### 实现任务

**T22. 修改 `src/agent/supervisor.py`** — ErrorEnvelope 包装

```python
# supervisor.py 顶部添加
from src.agent.schemas import (
    ErrorEnvelope, ErrorType, StructuredAgentError,
    _get_or_create_trace_id, ERROR_CODES,
)

# supervisor.py 约 L328-331
try:
    # ... 原有逻辑 ...
except Exception as e:
    logger.error(f"[Supervisor] Execution failed: {e}", exc_info=True)
    trace_id = _get_or_create_trace_id()
    env = ErrorEnvelope.from_exception(
        e,
        error_code="SUPERVISOR_AGENT_ERROR",
        trace_id=trace_id,
        context={"graph_id": graph_id, "execution_id": execution_id},
    )
    state.status = "failed"
    state.error = env.to_dict()  # ✅ 结构化错误
```

#### P5.1 测试覆盖

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_supervisor_run_returns_structured_error` | 失败时 error 为 ErrorEnvelope | Mock |
| `test_supervisor_stream_yields_error_envelope` | SSE 流错误包含 envelope | Mock |
| `test_supervisor_review_triggers_retry` | review="retry" 触发重试 | Mock |

#### P5.1 验收标准

- [ ] `state.error` 类型为 `dict`（ErrorEnvelope.to_dict()）
- [ ] 包含 `error_code`, `error_type`, `message`, `trace_id`
- [ ] `test_supervisor.py` 所有新增用例通过

---

### P5.2 Orchestrator 重试接入

#### 现状
`orchestrator_v2.py:152-167` 手动 3 次重试，无退避。

#### 实现任务

**T23. 修改 `src/agent/orchestrator_v2.py`** — 接入重试装饰器

```python
# orchestrator_v2.py 顶部添加
from src.agent.schemas import ErrorEnvelope, StructuredAgentError
from src.agent.retry_handler import retry_with_backoff, LLMRetryConfig

class DynamicOrchestrator:
    @retry_with_backoff(
        config=LLMRetryConfig(max_retries=2, initial_delay=2.0),
        check_budget=True,
    )
    async def plan(self, orchestration_id: str, input_text: str, thread_id: str):
        # ... 原有 plan 逻辑，移除手动重试循环 ...
        try:
            response = await asyncio.to_thread(self.llm.invoke, messages)
            # ... 解析 ...
        except StructuredAgentError:
            raise
        except Exception as e:
            raise StructuredAgentError.from_exception(
                e,
                context={"phase": "plan", "orchestration_id": orchestration_id}
            )
```

#### P5.2 测试覆盖

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_plan_retries_on_llm_error` | plan LLM 错误重试 | Mock |
| `test_execute_step_uses_structured_error` | 步骤错误使用 ErrorEnvelope | Mock |
| `test_orchestrator_step_error_structure` | step.error 为结构化 dict | Mock |

#### P5.2 验收标准

- [ ] `plan()` 被 `@retry_with_backoff` 包装
- [ ] `step.error` 为 ErrorEnvelope.to_dict() 结构
- [ ] 重试 2 次后失败才上报
- [ ] `test_orchestrator_v2.py` 新增用例通过

---

## P6 — ACP / CLI 对齐

### P6.1 ACP Server ErrorEnvelope

#### 现状
`acp_server.py:85` 返回 `str(e)` 而非 ErrorEnvelope。

#### 实现任务

**T24. 修改 `src/agent/acp_server.py`**

```python
# acp_server.py 顶部添加
from src.agent.schemas import ErrorEnvelope, ErrorType, _get_or_create_trace_id

# acp_server.py 约 L60-95 handle_request
def handle_request(self, method: str, params: dict, req_id) -> ACPResponse:
    try:
        # ... 原有路由逻辑 ...
    except Exception as e:
        trace_id = _get_or_create_trace_id()
        env = ErrorEnvelope.from_exception(
            e,
            trace_id=trace_id,
            context={"method": method, "params": params},
        )
        return ACPResponse(
            id=req_id,
            error=env.to_jsonrpc(),  # ✅ JSON-RPC 标准格式
        )
```

**T25. 修改 `src/agent/acp_client.py`**

```python
# acp_client.py 约 L159
# 原始: return f"Error: {str(e)}"
# 修改为:
from src.agent.schemas import ErrorEnvelope, ErrorType

if "error" in result:
    env_data = result["error"]
    return f"Error [{env_data.get('code', -32000)}] {env_data.get('message', str(e))}"
return "No response"
```

#### P6.1 测试覆盖

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_acp_server_returns_jsonrpc_error` | JSON-RPC 错误格式 | Mock |
| `test_acp_client_parses_error_code` | 错误码解析 | Mock |
| `test_acp_error_envelope_fields` | error 包含所有字段 | Mock |

#### P6.1 验收标准

- [ ] ACP server 错误返回 JSON-RPC 2.0 标准格式
- [ ] 包含 `code`, `message`, `data` 字段
- [ ] `test_acp.py` 所有新增用例通过

---

## P7 — API 层对齐

### P7.1 统一错误中间件

#### 现状
FastAPI server.py 使用 3 种错误格式混合。

#### 实现任务

**T26. 修改 `server.py`** — 统一错误处理中间件

```python
# server.py 顶部添加
from fastapi import Request
from fastapi.responses import JSONResponse
from src.agent.schemas import (
    StructuredAgentError, ErrorEnvelope, ErrorType,
    ErrorLevel, _get_or_create_trace_id,
)

# 约 L1-20 (导入区域后)
@app.exception_handler(StructuredAgentError)
async def structured_agent_error_handler(request: Request, exc: StructuredAgentError):
    """StructuredAgentError → 统一 JSONResponse"""
    env = exc.to_envelope()
    status_map = {
        ErrorLevel.LOW: 200,
        ErrorLevel.MEDIUM: 200,
        ErrorLevel.HIGH: 400,
        ErrorLevel.CRITICAL: 500,
    }
    status_code = status_map.get(env.error_level, 200)
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "failed",
            "error": env.to_dict(),
            "trace_id": env.trace_id,
            "trace_url": f"{os.getenv('LANGSMITH_TRACE_URL', '')}{env.trace_id}",
        }
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    """未捕获异常 → 包装为 StructuredAgentError"""
    env = ErrorEnvelope.from_exception(
        exc,
        error_code="INTERNAL_ERROR",
        trace_id=_get_or_create_trace_id(),
        context={"path": request.url.path},
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": env.to_dict(),
            "trace_id": env.trace_id,
        }
    )
```

#### P7.1 测试覆盖

| 测试用例 | 测试内容 | Mock/Real |
|---------|---------|-----------|
| `test_api_agent_error_returns_json` | AgentError → JSON 响应 | Mock |
| `test_api_generic_error_wrapped` | 未捕获异常 → ErrorEnvelope | Mock |
| `test_api_error_trace_id_propagated` | trace_id 在响应中 | Mock |
| `test_api_multiple_endpoints_same_error_format` | 所有端点同一格式 | Mock |

#### P7.1 验收标准

- [ ] 全局异常处理器注册
- [ ] `StructuredAgentError` → JSONResponse with ErrorEnvelope
- [ ] 所有端点使用统一错误格式 `{"status", "error", "trace_id"}`
- [ ] `test_api_error_format.py` 所有用例通过

---

## P8 — 测试覆盖补齐

### 测试文件清单

| 文件 | 覆盖内容 | 数量 |
|------|---------|------|
| `tests/test_error_envelope.py` | ErrorEnvelope 构造/序列化/ERROR_CODES | 8 |
| `tests/test_error_integration.py` | structured_catch 装饰器 | 4 |
| `tests/test_structured_catch.py` | 装饰器功能 | 7 |
| `tests/test_retry_handler.py` | 重试机制 | 8 |
| `tests/test_retry_integration.py` | 重试接入执行路径 | 4 |
| `tests/test_no_swallowed_exceptions.py` | 无吞没异常 | 5 |
| `tests/test_agent_protocol.py` | AgentInput/Output 契约 | 8 |
| `tests/test_agent_routing.py` | max_steps/max_iterations 路由 | 5 |
| `tests/test_agent_lifecycle.py` | pause/resume/abort | 6 |
| `tests/test_human_in_loop.py` | HITL Bug 修复验证 | 7 |
| `tests/test_tool_results.py` | 结构化 ToolResult | 10 |
| `tests/test_idempotency_key.py` | 幂等键机制 | 4 |
| `tests/test_compression.py` | CompressionResult 结构化 | 6 |
| `tests/test_long_term.py` | 存储异常处理 | 4 |
| `tests/test_supervisor.py` | Supervisor 结构化错误 | 4 |
| `tests/test_api_error_format.py` | API 错误格式统一 | 5 |

**总计**: 91 个新测试用例

### Real API 测试

| 测试 | 文件 | 环境变量 |
|------|------|---------|
| `test_run_with_real_api` | `test_agent_protocol.py` | `USE_REAL_API=true` |
| `test_llm_summarize_with_real_api` | `test_compression.py` | `USE_REAL_API=true` |
| `test_enrich_turns_with_llm_real_api` | `test_compression.py` | `USE_REAL_API=true` |

---

## 📋 实施顺序（更新版）

```
🔴 P0 人工干预
 └── T15  human_in_loop.py Bug 修复 ← asyncio.Event.wait() 返回 None，阻塞所有审批

P1 (基础协议层)
 ├── T1  schemas/agent_protocol.py  ← 第一个创建（解决循环依赖）
 ├── T2  schemas/__init__.py
 ├── T3  structured_catch 装饰器
 ├── T4  retry_handler 增强（导入 schemas/）
 ├── T5  agent.py 接入重试（@retry_with_backoff on _node_think）
 ├── T6  ~~compression.py~~ 已无吞没问题
 ├── T7  tools/__init__.py:213 修复吞没
 └── T8  orchestrator_checkpoint.py:141 修复吞没
 │
 ▼
P2 (Agent 层对齐)
 ├── T9   AgentInput/Output 重构
 ├── T10  state.py 添加 step_count 字段
 ├── T11  config.py max_steps 配置
 ├── T12  _should_continue 检查步数（已有 MAX_ITERATIONS，需整合）
 ├── T13  step_count 递增
 ├── T14  pause/resume/abort
 └── T16  orchestrator_v2.py Bug 修复
 │
 ▼
P3 (上下文系统)
 ├── T17  CompressionResult.errors 字段
 └── T18  long_term.py 异常处理
 │
 ▼
P4 (工具层)
 ├── T19  schemas/tool_result.py
 └── T20  所有工具结构化返回
 │
 ▼
P5 (编排层)
 ├── T21  agent.py 幂等键
 ├── T22  supervisor.py ErrorEnvelope
 └── T23  orchestrator_v2.py 重试
 │
 ▼
P6 (ACP/CLI)
 ├── T24  acp_server.py ErrorEnvelope
 └── T25  acp_client.py 错误解析
 │
 ▼
P7 (API 层)
 └── T26  server.py 统一中间件
 │
 ▼
P8 (测试覆盖)  ← 贯穿全程，每个 T 后写测试
```

---

## 🔧 辅助命令

```bash
# 验证吞没异常（应为 0 或仅限 finally 清理块）
grep -rn "except:" src/agent/ | grep -v "finally"
grep -rn "except Exception: continue" src/agent/

# 验证重试装饰器已应用
grep -rn "@retry_with_backoff" src/agent/

# 验证 ErrorEnvelope 已导入
grep -rn "from.*schemas.*import.*ErrorEnvelope" src/agent/

# 运行所有新增测试
python -m pytest tests/test_error_envelope.py \
                 tests/test_structured_catch.py \
                 tests/test_retry_handler.py \
                 tests/test_retry_integration.py \
                 tests/test_no_swallowed_exceptions.py \
                 tests/test_agent_protocol.py \
                 tests/test_agent_routing.py \
                 tests/test_agent_lifecycle.py \
                 tests/test_human_in_loop.py \
                 tests/test_tool_results.py \
                 tests/test_idempotency_key.py \
                 tests/test_compression.py \
                 tests/test_long_term.py \
                 tests/test_supervisor.py \
                 tests/test_api_error_format.py -v
```

# Real API 测试
USE_REAL_API=true python -m pytest tests/test_agent_protocol.py tests/test_compression.py -v
```

---

## 📝 文档更新

每个阶段完成后，同步更新:

1. **README.md** — 新增模块架构图、API 端点列表
2. **AGENTS.md** — 更新开发规范（错误处理、重试策略）
3. **docs/architecture/agent-flow-design.md** — 标注已实现条款

---

*最后更新: 2026-05-17*