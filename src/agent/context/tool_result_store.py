from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolResultSummary:
    """Tool Result 的摘要 + 元数据"""
    tool_call_id: str
    tool_name: str
    summary: str
    status: str  # success / failed
    timestamp: str
    access_count: int = 0


class ToolResultStore:
    """Tool Result 存储管理器 - LRU + 热度双因素淘汰

    设计参考: docs/context_design.md 4.1 节
    """

    def __init__(self, hot_zone_size: int = 5):
        self._cache: dict[str, dict] = {}  # tool_call_id -> full result
        self._hot_zone: list[ToolResultSummary] = []
        self._hot_zone_size = hot_zone_size

    def store(
        self,
        tool_call_id: str,
        tool_name: str,
        result: str,
        status: str = "success",
    ) -> ToolResultSummary:
        """存储 Tool Result，执行双因素淘汰后返回摘要"""
        now = datetime.now().isoformat()
        summary = self._generate_summary(tool_name, result, status)

        # 缓存完整结果
        self._cache[tool_call_id] = {
            "result": result,
            "tool_name": tool_name,
            "status": status,
            "timestamp": now,
            "summary": summary,
        }

        hot_entry = ToolResultSummary(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            summary=summary,
            status=status,
            timestamp=now,
            access_count=0,
        )

        # 双因素淘汰: LRU + 热度
        if len(self._hot_zone) >= self._hot_zone_size:
            self._evict()

        self._hot_zone.append(hot_entry)
        logger.debug(f"[ToolResultStore] Stored {tool_call_id}, hot_zone size: {len(self._hot_zone)}")
        return hot_entry

    def access(self, tool_call_id: str) -> dict | None:
        """访问记录: 提升热度并更新 LRU 顺序"""
        if tool_call_id not in self._cache:
            return None

        # 在 Hot Zone 中提升热度
        for entry in self._hot_zone:
            if entry.tool_call_id == tool_call_id:
                entry.access_count += 1
                # 移到末尾(LRU)
                self._hot_zone.remove(entry)
                self._hot_zone.append(entry)
                break

        return self._cache[tool_call_id]

    def get(self, tool_call_id: str) -> dict | None:
        """获取完整结果(不更新热度)"""
        return self._cache.get(tool_call_id)

    def get_hot_zone(self) -> list[ToolResultSummary]:
        """获取当前 Hot Zone"""
        return list(self._hot_zone)

    def get_all_summaries(self) -> list[ToolResultSummary]:
        """获取所有摘要(含已被淘汰出 Hot Zone 的)"""
        return [
            ToolResultSummary(
                tool_call_id=tid,
                tool_name=data["tool_name"],
                summary=data["summary"],
                status=data["status"],
                timestamp=data["timestamp"],
                access_count=next(
                    (e.access_count for e in self._hot_zone if e.tool_call_id == tid), 0
                ),
            )
            for tid, data in self._cache.items()
        ]

    def _evict(self) -> None:
        """双因素淘汰: 热度(访问次数)最低的移出 Hot Zone"""
        if not self._hot_zone:
            return
        # 按热度升序，再按时间升序
        sorted_zone = sorted(
            self._hot_zone,
            key=lambda e: (e.access_count, e.timestamp),
        )
        evicted = sorted_zone[0]
        self._hot_zone.remove(evicted)
        logger.debug(f"[ToolResultStore] Evicted {evicted.tool_call_id} (heat={evicted.access_count})")

    def _generate_summary(self, tool_name: str, result: str, status: str) -> str:
        """根据工具类型生成摘要"""
        if status == "failed":
            return f"[{tool_name}] 调用失败"
        result_preview = result[:200] if len(result) > 200 else result
        return f"[{tool_name}] {result_preview}"

    def __len__(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
        self._hot_zone.clear()
