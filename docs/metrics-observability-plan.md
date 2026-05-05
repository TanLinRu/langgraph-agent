# Metrics & Observability Plan

> LLM Agent 指标采集、持久化、UI 可视化方案 -- 让用户实时感知系统运行状态。

---

## 1. Current State

### What Exists

| Component | Location | Data | Limitation |
|-----------|----------|------|-----------|
| Agent `_metrics` | `agent.py:123` | requests, tokens, cost, latency, tool_calls, compressions | 内存 dict，重启丢失 |
| OpenCode `_metrics` | `opencode_agent.py:108` | requests, calls, errors, latency | 独立 dict，无 token 计数 |
| Orchestrator metrics | `orchestrator.py:470` | llm_calls, cost_usd, tokens | 与 agent.py 重复的 MODEL_COSTS |
| EventBus | `event_bus.py:24` | 4 种事件：agent_status, skill_trigger, task_progress, step_complete | 事件不携带指标数据 |
| EventBusCallback | `event_callback.py` | 映射 LangGraph 回调到 EventBus | 无 token/latency 透传 |
| `GET /metrics` | `server.py:220` | 返回 agent.get_metrics() | 单 agent 实例，无聚合 |
| Dashboard store | `dashboard.ts:46` | 消费 SSE 事件 | 只展示状态，无指标趋势 |

### Industry Comparison

| Capability | Ours | Langfuse | LangSmith | OpenLLMetry |
|------------|------|----------|-----------|-------------|
| Trace collection | Partial (EventBus) | Full | Full | Full |
| Token/cost tracking | In-memory only | Persistent + per-trace | Persistent + dashboard | OTel metrics |
| Latency percentiles | None | p50/p95/p99 | p50/p95/p99 | Histogram |
| Tool call tracing | EventBus events | Nested spans | Nested spans | OTel spans |
| User feedback | None | 1-5 score per trace | Thumbs up/down | Custom attributes |
| Prompt versioning | None | Yes | Yes | No |
| Self-hosted | Yes | Yes (MIT) | No (SaaS) | Yes (Apache 2.0) |
| OTel compatible | No | Yes (via SDK) | Partial | Native |

---

## 2. Architecture: Three-Layer Metrics

```
┌──────────────────────────────────────────────────────────────┐
│                    Layer 3: Presentation                      │
│  Vue Dashboard ─── Pinia metricsStore ─── SSE/REST API       │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────────────┐    │
│  │ Token    │  │ Latency      │  │ Agent Activity       │    │
│  │ Usage    │  │ Trends       │  │ Timeline             │    │
│  │ Gauge    │  │ (p50/p95)    │  │ (Gantt-style)        │    │
│  ├──────────┤  ├──────────────┤  ├─────────────────────┤    │
│  │ Cost     │  │ Error Rate   │  │ Tool Call            │    │
│  │ Breakdown│  │ Sparkline    │  │ Heatmap              │    │
│  ├──────────┤  ├──────────────┤  ├─────────────────────┤    │
│  │ Workflow │  │ System       │  │ Execution            │    │
│  │ Progress │  │ Health       │  │ History Table        │    │
│  └──────────┘  └──────────────┘  └─────────────────────┘    │
├──────────────────────────────────────────────────────────────┤
│                    Layer 2: Aggregation & Storage             │
│  MetricsCollector ──┬── SQLite (time-series)                 │
│                     ├── EventBus (real-time SSE)             │
│                     └── Prometheus exporter (optional)        │
├──────────────────────────────────────────────────────────────┤
│                    Layer 1: Collection                        │
│  LangGraph Callbacks ─┬─ LLM call span (tokens, latency)    │
│                       ├─ Tool call span (name, duration)     │
│                       ├─ Agent span (start/end/status)       │
│                       └─ System span (memory, queue depth)   │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 1: Collection

### 3.1 Unified Metrics Callback

Replace the current split between `EventBusCallbackHandler` (events only) and `_metrics` dicts (agent-level) with a single callback that feeds both.

```python
# src/agent/metrics_collector.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time
import asyncio
from typing import Optional

class MetricType(Enum):
    COUNTER = "counter"       # monotonically increasing (total_tokens, total_requests)
    GAUGE = "gauge"           # current value (active_agents, queue_depth)
    HISTOGRAM = "histogram"   # distribution (latency, tokens_per_request)
    EVENT = "event"           # discrete occurrence (tool_call, error, compression)

@dataclass
class MetricPoint:
    """Single metric observation."""
    name: str
    type: MetricType
    value: float
    labels: dict[str, str] = field(default_factory=dict)  # agent_id, model, tool_name, ...
    timestamp: datetime = field(default_factory=datetime.utcnow)
    execution_id: str | None = None
    turn_id: str | None = None

@dataclass
class TraceSpan:
    """Hierarchical trace span (OTel-compatible concept)."""
    span_id: str
    parent_id: str | None
    name: str                    # "llm_call", "tool_call", "agent_step", "workflow"
    start_time: float
    end_time: float | None = None
    status: str = "ok"           # "ok" | "error" | "timeout"
    attributes: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)  # timestamped annotations


class MetricsCollector:
    """Central metrics collection with EventBus bridge."""

    def __init__(self, event_bus, store, max_spans: int = 1000):
        self._event_bus = event_bus
        self._store = store                     # MetricsStore (SQLite)
        self._counters: dict[str, float] = {}   # cumulative counters
        self._gauges: dict[str, float] = {}     # current gauges
        self._histograms: dict[str, list[float]] = {}  # recent values
        self._active_spans: dict[str, TraceSpan] = {}
        self._completed_spans: list[TraceSpan] = []
        self._max_spans = max_spans
        self._flush_interval = 10.0  # seconds
        self._flush_task: asyncio.Task | None = None

    # --- Counter/Gauge/Histogram API ---

    def increment(self, name: str, value: float = 1.0, **labels) -> None:
        """Increment a counter (total_tokens, total_requests, ...)."""
        key = self._label_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def set_gauge(self, name: str, value: float, **labels) -> None:
        """Set a gauge to current value (active_agents, queue_depth, ...)."""
        key = self._label_key(name, labels)
        self._gauges[key] = value

    def observe(self, name: str, value: float, **labels) -> None:
        """Record a histogram observation (latency, tokens_per_request, ...)."""
        key = self._label_key(name, labels)
        bucket = self._histograms.setdefault(key, [])
        bucket.append(value)
        if len(bucket) > 500:
            bucket.pop(0)  # keep last 500 for percentile calculation

    # --- Trace Span API ---

    def start_span(self, name: str, parent_id: str | None = None, **attrs) -> str:
        """Start a trace span. Returns span_id."""
        span_id = f"span_{int(time.time()*1000)}_{id(self)}"
        span = TraceSpan(
            span_id=span_id,
            parent_id=parent_id,
            name=name,
            start_time=time.time(),
            attributes=attrs,
        )
        self._active_spans[span_id] = span
        return span_id

    def end_span(self, span_id: str, status: str = "ok", **result_attrs) -> None:
        """End a trace span and record metrics from it."""
        span = self._active_spans.pop(span_id, None)
        if not span:
            return
        span.end_time = time.time()
        span.status = status
        span.attributes.update(result_attrs)

        duration = span.end_time - span.start_time
        self.observe(f"{span.name}_duration", duration, **span.attributes)

        if span.name == "llm_call":
            self.increment("total_llm_calls", **span.attributes)
            if "total_tokens" in span.attributes:
                self.increment("total_tokens", span.attributes["total_tokens"], **span.attributes)
            if "cost_usd" in span.attributes:
                self.increment("total_cost_usd", span.attributes["cost_usd"], **span.attributes)

        if span.name == "tool_call":
            self.increment("total_tool_calls", **span.attributes)
            self.observe("tool_call_duration", duration, tool=span.attributes.get("tool_name", ""))

        if status == "error":
            self.increment("total_errors", **span.attributes)

        self._completed_spans.append(span)
        if len(self._completed_spans) > self._max_spans:
            self._completed_spans = self._completed_spans[-self._max_spans//2:]

        # Bridge to EventBus for real-time UI
        self._event_bus.publish_nowait({
            "event_type": "metric_update",
            "data": {
                "span_name": span.name,
                "duration_ms": duration * 1000,
                "status": status,
                **span.attributes,
            },
            "timestamp": datetime.utcnow().isoformat(),
        })

    # --- Snapshot & Query ---

    def get_snapshot(self) -> dict:
        """Current state for REST API or SSE snapshot."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                k: self._percentiles(v)
                for k, v in self._histograms.items()
            },
            "active_spans": len(self._active_spans),
            "completed_spans": len(self._completed_spans),
        }

    def get_time_series(self, metric_name: str, minutes: int = 60) -> list[dict]:
        """Query historical time-series from store."""
        return self._store.query(metric_name, minutes)

    # --- Internal ---

    def _label_key(self, name: str, labels: dict) -> str:
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}" if label_str else name

    def _percentiles(self, values: list[float]) -> dict:
        if not values:
            return {"p50": 0, "p95": 0, "p99": 0, "count": 0}
        s = sorted(values)
        n = len(s)
        return {
            "p50": s[int(n * 0.5)],
            "p95": s[int(n * 0.95)],
            "p99": s[int(n * 0.99)],
            "count": n,
            "min": s[0],
            "max": s[-1],
            "avg": sum(s) / n,
        }

    async def _flush_loop(self):
        """Periodically flush metrics to persistent store."""
        while True:
            await asyncio.sleep(self._flush_interval)
            await self._store.batch_write(self._counters, self._gauges, self._histograms)
```

### 3.2 LangGraph Callback Integration

```python
# src/agent/metrics_callback.py  (replaces event_callback.py)

from langchain_core.callbacks import BaseCallbackHandler
from .metrics_collector import MetricsCollector

class MetricsCallbackHandler(BaseCallbackHandler):
    """Bridges LangGraph lifecycle events to MetricsCollector + EventBus."""

    def __init__(self, collector: MetricsCollector, execution_id: str):
        super().__init__()
        self._collector = collector
        self._execution_id = execution_id
        self._active_spans: dict[str, str] = {}  # run_id -> span_id

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        span_id = self._collector.start_span(
            "llm_call",
            execution_id=self._execution_id,
            model=serialized.get("name", "unknown"),
        )
        self._active_spans[str(run_id)] = span_id

    def on_llm_end(self, response, *, run_id, **kwargs):
        span_id = self._active_spans.pop(str(run_id), None)
        if not span_id:
            return
        usage = response.llm_output.get("usage", {}) if response.llm_output else {}
        self._collector.end_span(
            span_id,
            total_tokens=usage.get("total_tokens", 0),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            cost_usd=self._estimate_cost(usage),
        )

    def on_llm_error(self, error, *, run_id, **kwargs):
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self._collector.end_span(span_id, status="error", error=str(error))

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        span_id = self._collector.start_span(
            "tool_call",
            execution_id=self._execution_id,
            tool_name=serialized.get("name", "unknown"),
        )
        self._active_spans[str(run_id)] = span_id

    def on_tool_end(self, output, *, run_id, **kwargs):
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self._collector.end_span(span_id, status="ok")

    def on_tool_error(self, error, *, run_id, **kwargs):
        span_id = self._active_spans.pop(str(run_id), None)
        if span_id:
            self._collector.end_span(span_id, status="error", error=str(error))

    def _estimate_cost(self, usage: dict) -> float:
        # delegate to unified cost calculator (no duplicate MODEL_COSTS)
        from .cost_calculator import estimate_cost
        return estimate_cost(
            model=self._current_model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
```

### 3.3 System Metrics Collector

```python
# src/agent/system_metrics.py

import asyncio
import psutil
from .metrics_collector import MetricsCollector

class SystemMetricsCollector:
    """Collects runtime system metrics every N seconds."""

    def __init__(self, collector: MetricsCollector, interval: float = 5.0):
        self._collector = collector
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while True:
            proc = psutil.Process()
            mem = proc.memory_info()
            self._collector.set_gauge("memory_rss_mb", mem.rss / 1024 / 1024)
            self._collector.set_gauge("memory_vms_mb", mem.vms / 1024 / 1024)
            self._collector.set_gauge("cpu_percent", proc.cpu_percent())
            self._collector.set_gauge("thread_count", proc.num_threads())
            await asyncio.sleep(self._interval)
```

### 3.4 Metrics to Collect

| Metric Name | Type | Labels | Source | UI Display |
|-------------|------|--------|--------|------------|
| `total_requests` | counter | agent_id, model | agent.py | 总请求计数 |
| `total_tokens` | counter | agent_id, model, type(prompt/completion) | LLM callback | Token 累计 |
| `total_cost_usd` | counter | agent_id, model | LLM callback | 成本累计 |
| `total_llm_calls` | counter | agent_id, model | LLM callback | LLM 调用次数 |
| `total_tool_calls` | counter | tool_name, agent_id | tool callback | 工具调用次数 |
| `total_errors` | counter | agent_id, error_type | callback | 错误累计 |
| `total_compressions` | counter | agent_id | compression.py | 压缩次数 |
| `active_agents` | gauge | - | supervisor | 当前活跃 Agent 数 |
| `queue_depth` | gauge | - | EventBus | 待处理事件队列深度 |
| `memory_rss_mb` | gauge | - | psutil | 进程内存 |
| `cpu_percent` | gauge | - | psutil | CPU 使用率 |
| `llm_call_duration` | histogram | agent_id, model | LLM callback | LLM 延迟分布 |
| `tool_call_duration` | histogram | tool_name | tool callback | 工具耗时分布 |
| `tokens_per_request` | histogram | model | LLM callback | 每次请求 Token 分布 |
| `agent_step_duration` | histogram | agent_id, step_name | chain callback | Agent 步骤耗时 |
| `workflow_duration` | histogram | graph_id | supervisor | 工作流总耗时 |
| `first_token_latency` | histogram | model | streaming callback | 首 Token 延迟 (TTFT) |

---

## 4. Layer 2: Aggregation & Storage

### 4.1 SQLite Time-Series Schema

```sql
-- metrics.db

CREATE TABLE metric_points (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,           -- counter|gauge|histogram
    value       REAL NOT NULL,
    labels      TEXT,                    -- JSON dict
    timestamp   TEXT NOT NULL,           -- ISO 8601
    execution_id TEXT,
    turn_id     TEXT
);

CREATE INDEX idx_metric_name_ts ON metric_points(name, timestamp);
CREATE INDEX idx_metric_execution ON metric_points(execution_id);

-- Pre-aggregated rollups for fast dashboard queries
CREATE TABLE metric_rollups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    period      TEXT NOT NULL,           -- 1m|5m|1h|1d
    period_start TEXT NOT NULL,
    count       INTEGER,
    sum         REAL,
    min         REAL,
    max         REAL,
    avg         REAL,
    p50         REAL,
    p95         REAL,
    p99         REAL,
    labels      TEXT
);

CREATE INDEX idx_rollup_name_period ON metric_rollups(name, period, period_start);

-- Trace spans for execution replay
CREATE TABLE trace_spans (
    span_id     TEXT PRIMARY KEY,
    parent_id   TEXT,
    name        TEXT NOT NULL,
    start_time  REAL NOT NULL,
    end_time    REAL,
    status      TEXT DEFAULT 'ok',
    attributes  TEXT,                    -- JSON dict
    execution_id TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX idx_span_execution ON trace_spans(execution_id);
CREATE INDEX idx_span_parent ON trace_spans(parent_id);
```

### 4.2 MetricsStore

```python
# src/agent/metrics_store.py

import sqlite3
import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional

class MetricsStore:
    """SQLite-backed metrics persistence with rollup aggregation."""

    def __init__(self, db_path: str = "memory/metrics.db"):
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(MIGRATION_SQL)

    async def write_point(self, point: MetricPoint) -> None:
        """Write a single metric point."""
        await asyncio.get_event_loop().run_in_executor(
            None, self._write_point_sync, point
        )

    async def batch_write(self, counters, gauges, histograms) -> None:
        """Batch flush accumulated metrics."""
        points = []
        ts = datetime.utcnow().isoformat()
        for key, value in counters.items():
            name, labels = self._parse_key(key)
            points.append((name, "counter", value, json.dumps(labels), ts))
        for key, value in gauges.items():
            name, labels = self._parse_key(key)
            points.append((name, "gauge", value, json.dumps(labels), ts))
        await asyncio.get_event_loop().run_in_executor(
            None, self._batch_insert, points
        )

    async def query(
        self,
        name: str,
        minutes: int = 60,
        labels: dict | None = None,
        rollup: str | None = None,
    ) -> list[dict]:
        """Query metric history. Use rollup for fast dashboard queries."""
        if rollup:
            return await self._query_rollup(name, rollup, minutes, labels)
        return await self._query_raw(name, minutes, labels)

    async def aggregate_rollups(self, period: str = "5m") -> None:
        """Aggregate raw points into rollup tables. Run periodically."""
        ...

    async def write_span(self, span: TraceSpan, execution_id: str) -> None:
        """Persist a completed trace span."""
        ...

    async def get_trace(self, execution_id: str) -> list[dict]:
        """Get all spans for an execution, tree-structured."""
        ...
```

### 4.3 Rollup Strategy

```
Raw data:     every metric point (high resolution, 7-day TTL)
  ↓ aggregate
1m rollups:   per-minute aggregates (30-day TTL)
  ↓ aggregate
5m rollups:   per-5-minute aggregates (90-day TTL)
  ↓ aggregate
1h rollups:   per-hour aggregates (1-year TTL)
  ↓ aggregate
1d rollups:   per-day aggregates (indefinite)
```

Dashboard queries hit rollup tables by default. Raw data available on drill-down.

### 4.4 EventBus Enhancement

Extend EventBus with a new `metric_update` event type:

```python
# In event_bus.py - add to event types
EVENT_TYPES = [
    "agent_status",       # existing
    "skill_trigger",      # existing
    "task_progress",      # existing
    "step_complete",      # existing
    "metric_update",      # NEW: carries metric deltas
    "system_health",      # NEW: system-level metrics
]
```

SSE payload for `metric_update`:
```json
{
    "event_type": "metric_update",
    "data": {
        "metric_name": "total_tokens",
        "delta": 1523,
        "cumulative": 48291,
        "labels": {"agent_id": "code-reviewer", "model": "gpt-4o"}
    },
    "timestamp": "2026-05-05T10:30:00Z"
}
```

---

## 5. Layer 3: Presentation (UI)

### 5.1 New API Endpoints

```
GET  /api/v1/metrics/snapshot           # current counters + gauges
GET  /api/v1/metrics/time-series        # ?name=total_tokens&minutes=60&rollup=5m
GET  /api/v1/metrics/percentiles        # ?name=llm_call_duration&minutes=60
GET  /api/v1/metrics/cost-breakdown     # by agent, by model, by time range
GET  /api/v1/metrics/system-health      # memory, cpu, queue depth
GET  /api/v1/traces/{execution_id}      # trace spans tree for an execution
GET  /api/v1/traces/{execution_id}/spans/{span_id}  # single span detail
SSE  /api/v1/events/stream              # existing, now includes metric_update events
```

### 5.2 Frontend Metrics Store

```typescript
// ui/src/stores/metrics.ts

interface MetricsState {
  // Real-time counters (updated via SSE)
  counters: Record<string, number>
  gauges: Record<string, number>

  // Time-series data (fetched on demand for charts)
  timeSeries: Record<string, TimeSeriesPoint[]>

  // Percentiles (for latency charts)
  percentiles: Record<string, PercentileData>

  // System health
  systemHealth: SystemHealth

  // Cost breakdown
  costBreakdown: CostBreakdown

  // Active traces
  activeTraces: Map<string, TraceSpan[]>
}

// Consumes metric_update SSE events to update counters in real-time
// Fetches time-series from REST API for chart rendering
// Auto-refreshes on interval (configurable, default 30s)
```

### 5.3 Dashboard Panels

#### Panel 1: Token Usage Gauge

```
┌─────────────────────────────────┐
│  Token Usage          [60m ▾]  │
│                                  │
│  ████████████████░░░░  78%      │
│  48,291 / 128,000 context       │
│                                  │
│  Prompt:  32,104  (66%)         │
│  Compl.:  16,187  (34%)         │
│                                  │
│  Trend: ▲ +2,341 last 10min    │
└─────────────────────────────────┘
```

#### Panel 2: Cost Breakdown

```
┌─────────────────────────────────┐
│  Cost Breakdown      [Today ▾]  │
│                                  │
│  gpt-4o        $1.23  ████████  │
│  gpt-4o-mini   $0.45  ███       │
│  gpt-4         $0.12  █         │
│                                  │
│  Total: $1.80                   │
│  vs yesterday: ▼ -$0.32 (-15%) │
└─────────────────────────────────┘
```

#### Panel 3: Latency Distribution

```
┌─────────────────────────────────┐
│  LLM Latency         [60m ▾]   │
│                                  │
│  p50:  1.2s  ████████░░        │
│  p95:  3.8s  ████████████████░  │
│  p99:  6.1s  ██████████████████ │
│                                  │
│  ▁▂▃▅▇█▇▅▃▂▁  (sparkline)     │
└─────────────────────────────────┘
```

#### Panel 4: Tool Call Heatmap

```
┌─────────────────────────────────┐
│  Tool Calls          [24h ▾]   │
│                                  │
│  execute_code    127  ████████  │
│  read_file        89  ██████    │
│  write_file       45  ███       │
│  search_files     34  ██        │
│  data_processor   12  █         │
│                                  │
│  Avg duration: 0.8s             │
│  Error rate: 2.3%               │
└─────────────────────────────────┘
```

#### Panel 5: Agent Activity Timeline

```
┌─────────────────────────────────┐
│  Agent Activity       [Live ▾]  │
│                                  │
│  code-reviewer  ████░░░░  3.2s  │
│  data-analyst   ████████  8.1s  │
│  email-writer   ██░░░░░░  1.5s  │
│                                  │
│  ● 3 active  ○ 5 idle           │
│  Queue: 2 pending               │
└─────────────────────────────────┘
```

#### Panel 6: Execution Trace (Drill-down)

```
┌─────────────────────────────────┐
│  Execution Trace  exec_abc123   │
│                                  │
│  supervisor.run     12.3s       │
│  ├─ code-reviewer    8.1s       │
│  │  ├─ llm_call      3.2s  1.2k│
│  │  ├─ read_file     0.1s      │
│  │  └─ llm_call      4.5s  2.1k│
│  └─ data-analyst     4.0s       │
│     ├─ llm_call      2.8s  0.9k│
│     └─ data_process  1.1s      │
│                                  │
│  Total tokens: 4,200            │
│  Total cost: $0.034             │
└─────────────────────────────────┘
```

### 5.4 UI Component Structure

```
ui/src/components/metrics/
├── MetricsDashboard.vue          # main container, layout grid
├── TokenUsageGauge.vue           # circular/linear gauge
├── CostBreakdown.vue             # stacked bar chart
├── LatencyChart.vue              # percentile bars + sparkline
├── ToolCallHeatmap.vue           # horizontal bar list
├── AgentTimeline.vue             # Gantt-style activity bars
├── ExecutionTrace.vue            # tree view with timing
├── SystemHealth.vue              # CPU/memory/queue indicators
└── MetricSparkline.vue           # reusable mini-chart component
```

### 5.5 Integration with Existing Dashboard Sidebar

The current `DashboardSidebar.vue` (360px/36px collapsible) already has panels for agent activity, skill triggers, task progress, and observation feed. Add a **Metrics** tab within the sidebar:

```
DashboardSidebar
├── [Activity]  ← existing panels
├── [Metrics]   ← NEW: shows gauges + sparklines
│   ├── Token gauge (mini)
│   ├── Cost today
│   ├── Latency p95
│   └── Error rate
└── [Trace]     ← NEW: execution trace drill-down
    └── clickable from any execution in Activity tab
```

---

## 6. Cost Calculator (Unified)

Eliminate the duplicate `MODEL_COSTS` in `agent.py:36` and `orchestrator.py:92`:

```python
# src/agent/cost_calculator.py

MODEL_COSTS: dict[str, dict[str, float]] = {
    # per 1M tokens
    "gpt-4":          {"input": 30.0,  "output": 60.0},
    "gpt-4-turbo":    {"input": 10.0,  "output": 30.0},
    "gpt-4o":         {"input": 2.5,   "output": 10.0},
    "gpt-4o-mini":    {"input": 0.15,  "output": 0.6},
    "gpt-3.5-turbo":  {"input": 0.5,   "output": 1.5},
    "claude-sonnet-4-6": {"input": 3.0,  "output": 15.0},
    "claude-haiku-4-5":  {"input": 0.8,  "output": 4.0},
    "deepseek-chat":  {"input": 0.14,  "output": 0.28},
    "qwen-plus":      {"input": 0.4,   "output": 1.2},
}

def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Calculate cost in USD. Returns 0 for unknown models."""
    costs = MODEL_COSTS.get(model, MODEL_COSTS.get(model.split(":")[-1]))
    if not costs:
        return 0.0
    return (prompt_tokens * costs["input"] + completion_tokens * costs["output"]) / 1_000_000

def get_model_info(model: str) -> dict:
    """Return cost info for a model."""
    costs = MODEL_COSTS.get(model, MODEL_COSTS.get(model.split(":")[-1]))
    return costs or {"input": 0, "output": 0, "unknown": True}
```

---

## 7. Prometheus Export (Optional)

For teams that already use Prometheus/Grafana:

```python
# src/agent/prometheus_export.py

from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Mirror MetricsCollector counters to Prometheus
llm_calls_total = Counter("agent_llm_calls_total", "Total LLM calls", ["agent_id", "model"])
tokens_total = Counter("agent_tokens_total", "Total tokens", ["agent_id", "model", "type"])
cost_usd_total = Counter("agent_cost_usd_total", "Total cost in USD", ["agent_id", "model"])
llm_latency = Histogram("agent_llm_latency_seconds", "LLM call latency", ["model"],
                         buckets=[0.5, 1, 2, 3, 5, 8, 13, 21])
tool_calls_total = Counter("agent_tool_calls_total", "Total tool calls", ["tool_name"])
active_agents = Gauge("agent_active_count", "Currently active agents")
errors_total = Counter("agent_errors_total", "Total errors", ["agent_id", "error_type"])

@app.get("/metrics/prometheus")
async def prometheus_metrics():
    return Response(generate_latest(), media_type="text/plain")
```

---

## 8. Implementation Phases

### Phase A: Collector + Store (Week 1)

- [x] Create `src/agent/metrics_collector.py` (MetricsCollector class)
- [x] Create `src/agent/metrics_store.py` (SQLite persistence + rollups)
- [x] Create `src/agent/cost_calculator.py` (unified MODEL_COSTS)
- [x] Create `src/agent/metrics_callback.py` (replace event_callback.py)
- [x] Create `src/agent/system_metrics.py` (psutil collector)
- [x] Wire into supervisor.py and server.py lifespan
- [x] Add new SSE event type `metric_update`
- [x] Tests for collector, store, cost calculator

### Phase B: API + Frontend Store (Week 2)

- [x] Add `/api/v1/metrics/*` endpoints to server.py
- [x] Add `/api/v1/traces/*` endpoints to server.py
- [x] Wire SSE metric_update events to dashboard store

### Phase C: Dashboard UI

- [x] Integrate into existing DashboardSidebar

---

## 9. Data Flow Summary

```
Agent executes LLM call
    │
    ▼
MetricsCallbackHandler.on_llm_end()
    │
    ├──▶ MetricsCollector.increment("total_tokens", 1523, agent="code-reviewer")
    ├──▶ MetricsCollector.observe("llm_call_duration", 3.2, model="gpt-4o")
    ├──▶ MetricsCollector.start_span("llm_call") / end_span()
    │
    ▼
MetricsCollector
    │
    ├──▶ EventBus.publish("metric_update", {...})  ──▶ SSE ──▶ dashboardStore
    │                                                          ──▶ TokenUsageGauge.vue (real-time)
    │
    ├──▶ MetricsStore.batch_write() (every 10s)    ──▶ SQLite
    │                                                          ──▶ /api/v1/metrics/time-series
    │                                                          ──▶ LatencyChart.vue (historical)
    │
    └──▶ MetricsStore.write_span()                 ──▶ trace_spans table
                                                             ──▶ /api/v1/traces/{id}
                                                             ──▶ ExecutionTrace.vue (drill-down)
```

Real-time path (SSE) updates gauges and sparklines instantly. Historical path (SQLite) powers charts and drill-down views. Both paths feed from the same `MetricsCollector`.
