"""
Orchestrator Checkpoint - 工作流检查点持久化

支持:
- 保存工作流状态到磁盘
- 启动时恢复未完成的工作流
- 定期检查点保存
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .state import OrchestratorState, OrchestratorStep

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = "memory/orchestrations"


class OrchestratorCheckpoint:
    """编排器检查点管理器"""

    def __init__(self, memory_dir: str = "memory"):
        self.memory_dir = Path(memory_dir)
        self.checkpoint_dir = self.memory_dir / "orchestrations"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _get_checkpoint_path(self, orchestration_id: str) -> Path:
        return self.checkpoint_dir / f"{orchestration_id}.json"

    def save(self, state: OrchestratorState) -> bool:
        """保存工作流状态"""
        try:
            path = self._get_checkpoint_path(state.orchestration_id)
            data = {
                "orchestration_id": state.orchestration_id,
                "thread_id": state.thread_id,
                "input_text": state.input_text,
                "plan_summary": state.plan_summary,
                "steps": [
                    {
                        "step_id": s.step_id,
                        "agent_id": s.agent_id,
                        "agent_name": s.agent_name,
                        "description": s.description,
                        "depends_on": s.depends_on,
                        "status": s.status,
                        "result": s.result,
                        "error": s.error,
                        "started_at": s.started_at,
                        "completed_at": s.completed_at,
                        "duration_ms": s.duration_ms,
                    }
                    for s in state.steps
                ],
                "status": state.status,
                "current_step_id": state.current_step_id,
                "final_output": state.final_output,
                "created_at": state.created_at,
                "updated_at": state.updated_at,
                "replan_count": state.replan_count,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"[Checkpoint] Failed to save {state.orchestration_id}: {e}")
            return False

    def load(self, orchestration_id: str) -> Optional[OrchestratorState]:
        """加载工作流状态"""
        try:
            path = self._get_checkpoint_path(orchestration_id)
            if not path.exists():
                return None
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            steps = [
                OrchestratorStep(
                    step_id=s["step_id"],
                    agent_id=s["agent_id"],
                    agent_name=s["agent_name"],
                    description=s["description"],
                    depends_on=s.get("depends_on", []),
                    status=s["status"],
                    result=s.get("result"),
                    error=s.get("error"),
                    started_at=s.get("started_at"),
                    completed_at=s.get("completed_at"),
                    duration_ms=s.get("duration_ms", 0),
                )
                for s in data.get("steps", [])
            ]
            return OrchestratorState(
                orchestration_id=data["orchestration_id"],
                thread_id=data["thread_id"],
                input_text=data["input_text"],
                plan_summary=data.get("plan_summary", ""),
                steps=steps,
                status=data["status"],
                current_step_id=data.get("current_step_id"),
                final_output=data.get("final_output"),
                created_at=data["created_at"],
                updated_at=data["updated_at"],
                replan_count=data.get("replan_count", 0),
            )
        except Exception as e:
            logger.error(f"[Checkpoint] Failed to load {orchestration_id}: {e}")
            return None

    def delete(self, orchestration_id: str) -> bool:
        """删除检查点"""
        try:
            path = self._get_checkpoint_path(orchestration_id)
            if path.exists():
                path.unlink()
            return True
        except Exception as e:
            logger.error(f"[Checkpoint] Failed to delete {orchestration_id}: {e}")
            return False

    def list_all(self) -> list[dict]:
        """列出所有检查点"""
        result = []
        for path in self.checkpoint_dir.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    result.append({
                        "orchestration_id": data["orchestration_id"],
                        "thread_id": data["thread_id"],
                        "input_text": data.get("input_text", "")[:80],
                        "status": data["status"],
                        "step_count": len(data.get("steps", [])),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                    })
            except Exception:
                continue
        return result

    def load_incomplete(self) -> list[OrchestratorState]:
        """加载所有未完成的工作流（用于恢复）"""
        incomplete = []
        for info in self.list_all():
            if info["status"] in ("planning", "running"):
                state = self.load(info["orchestration_id"])
                if state:
                    incomplete.append(state)
        return incomplete


_checkpoint: Optional[OrchestratorCheckpoint] = None


def get_checkpoint(memory_dir: str = "memory") -> OrchestratorCheckpoint:
    """获取检查点管理器单例"""
    global _checkpoint
    if _checkpoint is None:
        _checkpoint = OrchestratorCheckpoint(memory_dir)
    return _checkpoint