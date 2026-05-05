import sqlite3
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .metrics_collector import TraceSpan


MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS metric_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    value REAL NOT NULL,
    labels TEXT,
    timestamp TEXT NOT NULL,
    execution_id TEXT,
    turn_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_metric_name_ts ON metric_points(name, timestamp);
CREATE INDEX IF NOT EXISTS idx_metric_execution ON metric_points(execution_id);

CREATE TABLE IF NOT EXISTS metric_rollups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    period TEXT NOT NULL,
    period_start TEXT NOT NULL,
    count INTEGER,
    sum REAL,
    min REAL,
    max REAL,
    avg REAL,
    p50 REAL,
    p95 REAL,
    p99 REAL,
    labels TEXT
);

CREATE INDEX IF NOT EXISTS idx_rollup_name_period ON metric_rollups(name, period, period_start);

CREATE TABLE IF NOT EXISTS trace_spans (
    span_id TEXT PRIMARY KEY,
    parent_id TEXT,
    name TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL,
    status TEXT DEFAULT 'ok',
    attributes TEXT,
    execution_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_span_execution ON trace_spans(execution_id);
CREATE INDEX IF NOT EXISTS idx_span_parent ON trace_spans(parent_id);
"""


class MetricsStore:
    def __init__(self, db_path: str = "memory/metrics.db"):
        self._db_path = db_path
        self._init_db()
        self._pending_points: list[dict] = []
        self._pending_spans: list[TraceSpan] = []

    def _init_db(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(MIGRATION_SQL)

    async def write_point(self, name: str, type_: str, value: float, labels: dict | None = None, execution_id: str | None = None) -> None:
        ts = datetime.utcnow().isoformat()
        self._pending_points.append({
            "name": name,
            "type": type_,
            "value": value,
            "labels": json.dumps(labels) if labels else "{}",
            "timestamp": ts,
            "execution_id": execution_id,
        })

    async def batch_write(self, counters: dict, gauges: dict, histograms: dict) -> None:
        if not self._pending_points and not self._pending_spans:
            return
        
        def _write():
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("BEGIN")
                try:
                    for pt in self._pending_points:
                        conn.execute(
                            "INSERT INTO metric_points (name, type, value, labels, timestamp, execution_id) VALUES (?, ?, ?, ?, ?, ?)",
                            (pt["name"], pt["type"], pt["value"], pt["labels"], pt["timestamp"], pt["execution_id"])
                        )
                    
                    for span in self._pending_spans:
                        conn.execute(
                            "INSERT INTO trace_spans (span_id, parent_id, name, start_time, end_time, status, attributes, execution_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                span.span_id,
                                span.parent_id,
                                span.name,
                                span.start_time,
                                span.end_time,
                                span.status,
                                json.dumps(span.attributes),
                                span.execution_id,
                                datetime.utcnow().isoformat(),
                            )
                        )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        
        await asyncio.get_event_loop().run_in_executor(None, _write)
        self._pending_points.clear()
        self._pending_spans.clear()

    async def query(self, name: str, minutes: int = 60, labels: dict | None = None) -> list[dict]:
        ts_start = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        
        def _query():
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM metric_points WHERE name = ? AND timestamp > ? ORDER BY timestamp DESC LIMIT 1000",
                    (name, ts_start)
                ).fetchall()
                return [dict(r) for r in rows]
        
        return await asyncio.get_event_loop().run_in_executor(None, _query)

    async def query_rollup(self, name: str, period: str = "5m", minutes: int = 60) -> list[dict]:
        ts_start = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        
        def _query():
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM metric_rollups WHERE name = ? AND period = ? AND period_start > ? ORDER BY period_start DESC",
                    (name, period, ts_start)
                ).fetchall()
                return [dict(r) for r in rows]
        
        return await asyncio.get_event_loop().run_in_executor(None, _query)

    async def get_trace(self, execution_id: str) -> list[dict]:
        def _query():
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM trace_spans WHERE execution_id = ? ORDER BY start_time",
                    (execution_id,)
                ).fetchall()
                return [dict(r) for r in rows]
        
        return await asyncio.get_event_loop().run_in_executor(None, _query)

    def add_pending_span(self, span: TraceSpan) -> None:
        self._pending_spans.append(span)


_metrics_store: Optional[MetricsStore] = None


def get_metrics_store() -> MetricsStore:
    global _metrics_store
    if _metrics_store is None:
        _metrics_store = MetricsStore()
    return _metrics_store


__all__ = ["MetricsStore", "get_metrics_store", "MIGRATION_SQL"]