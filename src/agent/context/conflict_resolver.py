from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ConflictType(Enum):
    """记忆冲突类型"""
    CONTRADICTION = "contradiction"    # 语义矛盾
    EVOLUTION = "evolution"           # 意图演进（允许保留历史）
    SPECIFICATION = "specification"    # 细化补充
    NO_CONFLICT = "no_conflict"


class MemoryOp(Enum):
    """记忆操作类型"""
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "noop"


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    namespace: tuple
    key: str
    value: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    value_history: list[dict] = field(default_factory=list)
    conflict_type: str | None = None
    current_value: str | None = None


def detect_conflict_type(old_value: str, new_value: str) -> ConflictType:
    """检测冲突类型（简化版，实际可用语义模型）

    设计参考: docs/context_design.md 6.1 节
    """
    if old_value == new_value:
        return ConflictType.NO_CONFLICT

    negation_words = ["不", "没", "不要", "不是", "没有", "不会", "不能"]
    has_negation_old = any(w in old_value for w in negation_words)
    has_negation_new = any(w in new_value for w in negation_words)

    if has_negation_old != has_negation_new:
        return ConflictType.CONTRADICTION

    # 细化补充: 新值包含旧值的语义扩展
    if len(new_value) > len(old_value) and old_value in new_value:
        return ConflictType.SPECIFICATION

    # 意图演进: 新旧值不矛盾但有发展
    return ConflictType.EVOLUTION


def resolve_memory_conflict(old_mem: MemoryEntry, new_value: str) -> tuple[MemoryOp, MemoryEntry]:
    """解决记忆冲突 - 保留历史轨迹

    设计参考: docs/context_design.md 6.2 节

    Returns:
        (操作类型, 更新后的记忆条目)
    """
    if old_mem.value == new_value:
        return (MemoryOp.NOOP, old_mem)

    conflict_type = detect_conflict_type(old_mem.value, new_value)
    now = datetime.now().isoformat()

    if conflict_type == ConflictType.CONTRADICTION:
        # 语义矛盾: 保留历史轨迹，不直接覆盖
        updated = MemoryEntry(
            id=old_mem.id,
            namespace=old_mem.namespace,
            key=old_mem.key,
            value=old_mem.value,
            current_value=new_value,
            created_at=old_mem.created_at,
            updated_at=now,
            value_history=old_mem.value_history + [
                {"value": old_mem.value, "timestamp": old_mem.updated_at}
            ],
            conflict_type=conflict_type.value,
        )
        return (MemoryOp.UPDATE, updated)

    elif conflict_type == ConflictType.EVOLUTION:
        # 意图演进: 允许直接更新
        updated = MemoryEntry(
            id=old_mem.id,
            namespace=old_mem.namespace,
            key=old_mem.key,
            value=new_value,
            created_at=old_mem.created_at,
            updated_at=now,
            value_history=old_mem.value_history,
            conflict_type=None,
        )
        return (MemoryOp.UPDATE, updated)

    else:
        # 细化补充/无冲突: 直接更新
        updated = MemoryEntry(
            id=old_mem.id,
            namespace=old_mem.namespace,
            key=old_mem.key,
            value=new_value,
            created_at=old_mem.created_at,
            updated_at=now,
            value_history=old_mem.value_history,
            conflict_type=None,
        )
        return (MemoryOp.UPDATE, updated)


def resolve_new_memory(new_mem: MemoryEntry) -> tuple[MemoryOp, MemoryEntry]:
    """处理新记忆插入"""
    return (MemoryOp.ADD, new_mem)
