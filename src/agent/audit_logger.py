"""
Audit Logger — structured error audit trail

Writes `fatal`/`system`-level errors to `memory/audit/{YYYY-MM-DD}.jsonl`
for compliance and post-mortem analysis.
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from .schemas import ErrorEnvelope, ErrorLevel

logger = logging.getLogger(__name__)

AUDIT_DIR = Path("./memory/audit")


def _ensure_audit_dir():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def _audit_path() -> Path:
    date_str = time.strftime("%Y-%m-%d")
    return AUDIT_DIR / f"{date_str}.jsonl"


def log_error(
    error: dict,
    trace_id: str = "",
    thread_id: str = "",
    user_id: str = "",
    context: Optional[dict] = None,
):
    """Write a structured error event to the audit log.

    Only writes if error's error_level >= HIGH or error_type is SYSTEM.
    """
    error_level = error.get("error_level", 0)
    error_type = error.get("error_type", "")

    if isinstance(error_level, str):
        try:
            error_level = ErrorLevel[error_level.upper()].value
        except (KeyError, ValueError):
            error_level = 0

    is_significant = (
        error_level >= ErrorLevel.HIGH.value
        or error_type.lower() == "system"
    )
    if not is_significant:
        return

    _ensure_audit_dir()

    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trace_id": trace_id,
        "thread_id": thread_id,
        "user_id": user_id,
        "error": error,
    }
    if context:
        record["context"] = context

    try:
        path = _audit_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.debug(f"[Audit] Wrote error to {path}")
    except Exception as e:
        logger.warning(f"[Audit] Failed to write audit log: {e}")
