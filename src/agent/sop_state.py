from typing import TypedDict, Optional, Literal, Union
from pathlib import Path
import json
import os
from datetime import datetime


class SOPState(TypedDict, total=False):
    """SOP State - mirrors personal-sop SOPState interface"""
    task_id: str
    sop: str
    status: Literal["in_progress", "completed", "failed"]
    started_at: str
    completed_at: Optional[str]
    business_requirements: Optional[dict]
    config: Optional[dict]
    current_step: int
    steps: dict
    answers: dict
    resume_from: Optional[str]


def get_state_dir() -> Path:
    """Get SOP state directory from config or default"""
    memory_dir = os.getenv("AGENT_MEMORY_DIR", "./memory")
    return Path(memory_dir) / ".sop" / "state"


def _ensure_state_dir() -> Path:
    """Ensure state directory exists"""
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _get_state_file_path(sop_name: str, date: str = None) -> Path:
    """Get state file path for given SOP name"""
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    state_dir = _ensure_state_dir()
    return state_dir / f"{sop_name}-{date}.json"


def list_state_files() -> list[str]:
    """List all SOP state files"""
    state_dir = get_state_dir()
    if not state_dir.exists():
        return []
    return sorted([f.name for f in state_dir.glob("*.json")])


def load_sop_state(sop_name: str, date: str = None) -> Optional[SOPState]:
    """Load SOP state by name and date (default: latest in_progress)"""
    state_dir = get_state_dir()
    if not state_dir.exists():
        return None

    if date:
        file_path = state_dir / f"{sop_name}-{date}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    matching = sorted([f for f in state_dir.glob(f"{sop_name}-*.json")], reverse=True)
    for f in matching:
        try:
            with open(f, "r", encoding="utf-8") as f:
                state = json.load(f)
                if state.get("status") == "in_progress":
                    return state
        except (json.JSONDecodeError, IOError):
            continue

    return None


def load_latest_in_progress() -> Optional[SOPState]:
    """Load latest in_progress SOP state"""
    state_dir = get_state_dir()
    if not state_dir.exists():
        return None

    matching = sorted(state_dir.glob("*.json"), reverse=True)
    for f in matching:
        try:
            with open(f, "r", encoding="utf-8") as f:
                state = json.load(f)
                if state.get("status") == "in_progress":
                    return state
        except (json.JSONDecodeError, IOError):
            continue

    return None


def save_sop_state(state: SOPState) -> None:
    """Save SOP state to file"""
    sop_name = state.get("sop", "unknown")
    started = state.get("started_at", "")
    date = started[:10].replace("-", "") if started else datetime.now().strftime("%Y%m%d")
    file_path = _get_state_file_path(sop_name, date)

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def update_sop_step(
    sop_name: str,
    step: str,
    status: Literal["pending", "in_progress", "completed"],
    answers: dict = None,
    date: str = None
) -> SOPState:
    """Update SOP step status"""
    state = load_sop_state(sop_name, date)
    if not state:
        state = {
            "task_id": f"{sop_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "sop": sop_name,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "current_step": 1,
            "steps": {},
            "answers": {},
        }

    if step:
        state["steps"][step] = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }

    if status == "in_progress":
        state["status"] = "in_progress"
    elif status == "completed":
        state["status"] = "completed"
        state["completed_at"] = datetime.now().isoformat()

    if answers:
        state["answers"] = state.get("answers", {})
        state["answers"][step] = answers

    save_sop_state(state)
    return state


def delete_sop_state(sop_name: str, date: str = None) -> bool:
    """Delete SOP state file"""
    file_path = _get_state_file_path(sop_name, date)
    if file_path.exists():
        file_path.unlink()
        return True
    return False


__all__ = [
    "SOPState",
    "get_state_dir",
    "list_state_files",
    "load_sop_state",
    "load_latest_in_progress",
    "save_sop_state",
    "update_sop_step",
    "delete_sop_state",
]