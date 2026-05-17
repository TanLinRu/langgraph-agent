from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class UserProfile:
    """用户画像数据模型

    存储用户偏好、已知背景、行为模式，注入到 system message 供 LLM 感知。
    持久化在 LongTermManager.memories 表中（namespace=tenant|org|user_id|profile）。
    """
    user_id: str
    tenant_id: str = "default"
    org_id: str = "default"
    preferences: dict = field(default_factory=lambda: {
        "language": "python",
        "verbose": True,
        "auto_execute": True,
    })
    known_context: list[str] = field(default_factory=list)
    behavior_patterns: dict = field(default_factory=lambda: {
        "avg_turns_per_session": 0.0,
        "tool_usage_ratio": 0.0,
        "total_sessions": 0,
        "common_tools": [],
    })
    last_updated: str = ""

    def to_system_block(self) -> str:
        """生成可注入到 system message 的文本块"""
        if not self.known_context and not self.preferences:
            return ""
        lines = ["## 用户画像"]
        if self.known_context:
            lines.append("### 已知背景")
            lines.extend(f"- {c}" for c in self.known_context)
        if self.preferences:
            lines.append("### 偏好设置")
            for k, v in self.preferences.items():
                lines.append(f"- {k}: {v}")
        return "\n".join(lines)
