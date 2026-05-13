from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
import json
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG
from .trace_context import get_trace_id


class AuditAction(Enum):
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    TOOL_EXEC = "tool_exec"
    WORKFLOW_CREATE = "workflow_create"
    WORKFLOW_DELETE = "workflow_delete"
    ORCHESTRATION_START = "orchestration_start"
    ORCHESTRATION_COMPLETE = "orchestration_complete"
    ROLLBACK = "rollback"
    API_WRITE = "api_write"
    AGENT_REGISTER = "agent_register"
    AGENT_DELETE = "agent_delete"


@dataclass
class AuditRecord:
    trace_id: str
    timestamp: str
    action: AuditAction
    actor: str
    target: str
    details: dict
    result: str


def _audit_dir() -> Path:
    base = DEFAULT_CONFIG.long_term.memory_dir / "audit"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _audit_path() -> Path:
    return _audit_dir() / f"{date.today().isoformat()}.jsonl"


def write_audit(
    action: AuditAction,
    actor: str,
    target: str,
    details: dict | None = None,
    result: str = "success",
) -> None:
    record = AuditRecord(
        trace_id=get_trace_id() or "no-trace",
        timestamp=datetime.utcnow().isoformat(),
        action=action,
        actor=actor,
        target=target,
        details=details or {},
        result=result,
    )
    with open(_audit_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
