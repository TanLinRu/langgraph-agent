import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None


from .metrics_collector import get_metrics_collector


class SystemMetricsCollector:
    def __init__(self, interval: float = 5.0):
        self._collector = get_metrics_collector()
        self._interval = interval
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if not PSUTIL_AVAILABLE:
            logger.warning("[SystemMetrics] psutil not available, skipping system metrics")
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("[SystemMetrics] Started")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[SystemMetrics] Stopped")

    async def _loop(self):
        while True:
            try:
                await self._collect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[SystemMetrics] Error: {e}")
            await asyncio.sleep(self._interval)

    async def _collect(self):
        if not PSUTIL_AVAILABLE:
            return

        proc = psutil.Process()
        mem = proc.memory_info()
        
        self._collector.set_gauge("memory_rss_mb", mem.rss / 1024 / 1024)
        self._collector.set_gauge("memory_vms_mb", mem.vms / 1024 / 1024)
        self._collector.set_gauge("cpu_percent", proc.cpu_percent())
        self._collector.set_gauge("thread_count", proc.num_threads())


_system_collector: Optional[SystemMetricsCollector] = None


def get_system_collector() -> SystemMetricsCollector:
    global _system_collector
    if _system_collector is None:
        _system_collector = SystemMetricsCollector()
    return _system_collector


__all__ = ["SystemMetricsCollector", "get_system_collector"]