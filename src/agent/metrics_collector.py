from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time
import asyncio
from typing import Optional


class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    EVENT = "event"


@dataclass
class MetricPoint:
    name: str
    type: MetricType
    value: float
    labels: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    execution_id: str | None = None
    turn_id: str | None = None


@dataclass
class TraceSpan:
    span_id: str
    name: str
    start_time: float
    parent_id: str | None = None
    end_time: float | None = None
    status: str = "ok"
    attributes: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    execution_id: str | None = None


class MetricsCollector:
    def __init__(self, max_spans: int = 1000):
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._active_spans: dict[str, TraceSpan] = {}
        self._completed_spans: list[TraceSpan] = []
        self._max_spans = max_spans

    def increment(self, name: str, value: float = 1.0, **labels) -> None:
        key = self._label_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def set_gauge(self, name: str, value: float, **labels) -> None:
        key = self._label_key(name, labels)
        self._gauges[key] = value

    def observe(self, name: str, value: float, **labels) -> None:
        key = self._label_key(name, labels)
        bucket = self._histograms.setdefault(key, [])
        bucket.append(value)
        if len(bucket) > 500:
            bucket.pop(0)

    def start_span(self, name: str, parent_id: str | None = None, **attrs) -> str:
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

    def end_span(self, span_id: str, status: str = "ok", **result_attrs) -> TraceSpan | None:
        span = self._active_spans.pop(span_id, None)
        if not span:
            return None
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

        return span

    def get_snapshot(self) -> dict:
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

    def get_counters(self) -> dict:
        return dict(self._counters)

    def get_gauges(self) -> dict:
        return dict(self._gauges)

    def get_histograms(self) -> dict:
        return {k: self._percentiles(v) for k, v in self._histograms.items()}

    def get_completed_spans(self) -> list[TraceSpan]:
        return list(self._completed_spans)

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


_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


__all__ = [
    "MetricType",
    "MetricPoint",
    "TraceSpan",
    "MetricsCollector",
    "get_metrics_collector",
]