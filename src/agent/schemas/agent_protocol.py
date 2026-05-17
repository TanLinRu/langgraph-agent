from dataclasses import dataclass, field
from typing import TypedDict, Literal, Optional, Callable, Any
from enum import Enum
from functools import wraps
import time
import logging
import uuid
import asyncio

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    RECOVERABLE = "recoverable"
    FATAL = "fatal"
    SYSTEM = "system"
    VALIDATION = "validation"


class ErrorLevel(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class ErrorEnvelope:
    error_code: str
    error_type: ErrorType
    message: str
    retryable: bool = True
    retry_after_ms: int = 0
    trace_id: str = ""
    context_snapshot: dict = field(default_factory=dict)
    fallback_action: str = "none"
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
    trace_id: str
    task: str
    tools: list[dict]
    config: dict
    context: dict
    session_id: Optional[str]


class AgentOutput(TypedDict):
    status: Literal["success", "failed", "timeout", "partial"]
    result: Any
    trace_log: list[dict]
    token_usage: dict
    cost_usd: float
    error: Optional[dict]
    trace_id: str
    steps_executed: int
    iterations: int
    ended_at: str
    task_status: Optional[str]
    compression_count: int


class StructuredAgentError(Exception):
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
        error_code: str = "INTERNAL_ERROR",
        error_type: ErrorType = ErrorType.RECOVERABLE,
        retryable: bool = True,
        error_level: ErrorLevel = ErrorLevel.MEDIUM,
    ) -> "StructuredAgentError":
        env = ErrorEnvelope.from_exception(
            exc,
            trace_id=trace_id,
            context=context,
            tool_name=tool_name,
            step=step,
        )
        return cls(
            error_code=error_code if error_code != "INTERNAL_ERROR" else env.error_code,
            error_type=error_type if error_type != ErrorType.RECOVERABLE else env.error_type,
            message=str(exc),
            retryable=retryable if retryable != True else env.retryable,
            trace_id=trace_id,
            context=context,
            error_level=error_level if error_level != ErrorLevel.MEDIUM else env.error_level,
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
        return str(uuid.uuid4())


ERROR_CODES: dict[str, dict] = {
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
    "COMPRESSION_FAILED": {
        "error_code": "COMPRESSION_FAILED",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    "VECTOR_STORE_INIT_ERROR": {
        "error_code": "VECTOR_STORE_INIT_ERROR",
        "error_type": ErrorType.SYSTEM,
        "retryable": False,
        "level": ErrorLevel.HIGH,
    },
    "VECTOR_SEARCH_ERROR": {
        "error_code": "VECTOR_SEARCH_ERROR",
        "error_type": ErrorType.RECOVERABLE,
        "retryable": True,
        "retry_after_ms": 1000,
        "level": ErrorLevel.LOW,
    },
}


def _safe_serialize_args(args, kwargs) -> dict:
    try:
        safe_kwargs = {k: str(v)[:200] for k, v in kwargs.items()}
        return {"args_count": len(args), "kwargs": safe_kwargs}
    except Exception:
        return {"args_count": len(args)}


def structured_catch(
    error_code: str = "INTERNAL_ERROR",
    error_type: ErrorType = ErrorType.RECOVERABLE,
    retryable: bool = True,
    fallback_action: str = "none",
    error_level: ErrorLevel = ErrorLevel.MEDIUM,
    log_level: str = "error",
    suppress: bool = False,
) -> Callable[[Callable], Callable]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            trace_id = _get_or_create_trace_id()
            context = {"func": func.__name__, "args": _safe_serialize_args(args, kwargs)}
            try:
                return func(*args, **kwargs)
            except StructuredAgentError:
                raise
            except Exception as e:
                logger.log(
                    getattr(logging, log_level.upper(), logging.ERROR),
                    f"[structured_catch] {func.__name__}: {e}",
                )
                if suppress:
                    logger.warning(
                        f"[structured_catch] {func.__name__} suppressed: {error_code}"
                    )
                    return None
                raise StructuredAgentError(
                    error_code=error_code,
                    error_type=error_type,
                    message=str(e),
                    retryable=retryable,
                    trace_id=trace_id,
                    context=context,
                    fallback_action=fallback_action,
                    error_level=error_level,
                )

        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            trace_id = _get_or_create_trace_id()
            context = {"func": func.__name__, "args": _safe_serialize_args(args, kwargs)}
            try:
                return await func(*args, **kwargs)
            except StructuredAgentError:
                raise
            except Exception as e:
                logger.log(
                    getattr(logging, log_level.upper(), logging.ERROR),
                    f"[structured_catch] {func.__name__}: {e}",
                )
                if suppress:
                    return None
                raise StructuredAgentError.from_exception(
                    e,
                    trace_id=trace_id,
                    context=context,
                    tool_name=func.__name__,
                    error_code=error_code,
                    error_type=error_type,
                    retryable=retryable,
                    error_level=error_level,
                )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator