from dataclasses import dataclass, field
from typing import Literal, Optional

from .agent_protocol import ErrorEnvelope, ErrorType


@dataclass
class ToolResult:
    status: Literal["success", "failed", "timeout", "partial"] = "success"
    content: str = ""
    error: Optional[dict] = None
    metadata: dict = field(default_factory=dict)
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