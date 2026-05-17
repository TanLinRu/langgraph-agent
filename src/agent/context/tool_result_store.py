from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Optional, Callable

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
    full_content: str = ""  # 热区条目保留完整原文
    is_hot: bool = False     # 是否在热区中


class ToolResultStore:
    """Tool Result 存储管理器 - LRU + 热度双因素淘汰

    设计参考: docs/context_design.md 4.1 节

    热区大小默认为 10（当前轮 + 前一轮），淘汰时触发 on_evict 回调写入 L3。
    """

    def __init__(
        self,
        hot_zone_size: int = 10,
        on_evict: Optional[Callable[[list[dict]], None]] = None,
    ):
        self._cache: dict[str, dict] = {}  # tool_call_id -> full result
        self._hot_zone: list[ToolResultSummary] = []
        self._hot_zone_size = hot_zone_size
        self._on_evict = on_evict

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
            full_content=result,  # 热区保留完整原文
            is_hot=True,
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
                full_content="",
                is_hot=tid in {e.tool_call_id for e in self._hot_zone},
            )
            for tid, data in self._cache.items()
        ]

    def _evict(self) -> None:
        """双因素淘汰: 热度最低的移出 Hot Zone，触发 L3 回调"""
        if not self._hot_zone:
            return
        sorted_zone = sorted(
            self._hot_zone,
            key=lambda e: (e.access_count, e.timestamp),
        )
        evicted = sorted_zone[0]
        self._hot_zone.remove(evicted)

        # 标记不再是热区
        evicted.is_hot = False
        evicted.full_content = ""

        # 触发 L3 持久化回调
        if self._on_evict:
            try:
                self._on_evict([{
                    "tool_call_id": evicted.tool_call_id,
                    "tool_name": evicted.tool_name,
                    "content": self._cache.get(evicted.tool_call_id, {}).get("result", ""),
                    "status": evicted.status,
                }])
            except Exception as e:
                logger.warning(f"[ToolResultStore] on_evict failed: {e}")

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
