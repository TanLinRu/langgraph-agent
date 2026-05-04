from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)


@dataclass
class ArchiveConfig:
    """归档配置"""
    enabled: bool = True
    schedule_cron: str = "0 2 * * *"  # 每天凌晨 2 点
    notification_callback: Optional[Callable[[str], None]] = None


class ArchiveManager:
    """归档管理器"""

    def __init__(self, config: ArchiveConfig, long_term_manager):
        self.config = config
        self.long_term = long_term_manager

    def run_archive(self) -> str:
        """执行归档，返回通知"""
        if not self.config.enabled:
            return "归档已禁用"

        archived_ids, notification = self.long_term.archive_old_sessions()

        if archived_ids:
            logger.info(f"归档了 {len(archived_ids)} 个会话: {archived_ids}")

            if self.config.notification_callback:
                try:
                    self.config.notification_callback(notification)
                except Exception as e:
                    logger.error(f"通知发送失败: {e}")

        return notification

    def get_archive_status(self) -> dict:
        """获取归档状态"""
        import os
        from pathlib import Path

        archive_dir = self.long_term.config.memory_dir / "archive"
        files = list(archive_dir.glob("*.jsonl")) if archive_dir.exists() else []

        return {
            "archived_count": len(files),
            "files": [f.name for f in files],
            "last_run": datetime.now().isoformat()
        }