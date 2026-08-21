"""Local metrics: counters, gauges, and latency histograms.

v2.md §7 sets acceptance targets as percentiles — partial latency p95 under
500 ms, delivery p95 under 700 ms — which are unfalsifiable without
instrumentation. This is that instrumentation.

Everything stays on the machine. No metric carries transcript text, and none
leaves the process except through the daemon's own API.

Histograms use fixed buckets rather than reservoir sampling: the buckets are
cheap, bounded, and give a stable p95 without retaining samples. Bucket
boundaries are in milliseconds and chosen around the targets they police.
"""
from __future__ import annotations

import threading
import time
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Iterator

#: Millisecond boundaries. Dense where the acceptance targets sit.
DEFAULT_BUCKETS: tuple[float, ...] = (
    5, 10, 25, 50, 100, 200, 300, 500, 700, 1000, 1500, 2000, 3000, 5000, 10000
)


class Histogram:
    """A bounded, cumulative latency histogram."""

    __slots__ = ("name", "unit", "buckets", "_counts", "_overflow", "_sum",
                 "_count", "_min", "_max", "_lock")

    def __init__(self, name: str, buckets: tuple[float, ...] = DEFAULT_BUCKETS,
                 unit: str = "ms") -> None:
        self.name = name
        self.unit = unit
        self.buckets = buckets
        self._counts = [0] * len(buckets)
        self._overflow = 0
        self._sum = 0.0
        self._count = 0
        self._min = float("inf")
        self._max = 0.0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            index = bisect_left(self.buckets, value)
            if index >= len(self.buckets):
                self._overflow += 1
            else:
                self._counts[index] += 1
            self._sum += value
            self._count += 1
            self._min = min(self._min, value)
            self._max = max(self._max, value)

    @property
    def count(self) -> int:
        return self._count

    def percentile(self, fraction: float) -> float:
        """Upper bound of the bucket containing the requested percentile.

        This over-reports within one bucket width, which is the honest
        direction for a latency budget: it never claims to be faster than it
        can prove.
        """
        with self._lock:
            if self._count == 0:
                return 0.0
            target = fraction * self._count
            seen = 0
            for index, bucket_count in enumerate(self._counts):
                seen += bucket_count
                if seen >= target:
                    return self.buckets[index]
            return self._max

    def snapshot(self) -> dict:
        with self._lock:
            if self._count == 0:
                return {"count": 0}
            mean = self._sum / self._count
        return {
            "count": self._count,
            "min": round(self._min, 1),
            "mean": round(mean, 1),
            "p50": self.percentile(0.50),
            "p95": self.percentile(0.95),
            "p99": self.percentile(0.99),
            "max": round(self._max, 1),
            "unit": self.unit,
        }

    def reset(self) -> None:
        with self._lock:
            self._counts = [0] * len(self.buckets)
            self._overflow = 0
            self._sum = 0.0
            self._count = 0
            self._min = float("inf")
            self._max = 0.0


class Timer:
    """Context manager that records elapsed wall time into a histogram."""

    __slots__ = ("_histogram", "_started", "elapsed_ms")

    def __init__(self, histogram: Histogram) -> None:
        self._histogram = histogram
        self._started = 0.0
        self.elapsed_ms = 0.0

    def __enter__(self) -> "Timer":
        self._started = time.perf_counter()
        return self

    def __exit__(self, *exc_info) -> None:
        self.elapsed_ms = (time.perf_counter() - self._started) * 1000.0
        # Record the failed attempt too; a fast failure that hides a broken
        # path is exactly what a latency budget should surface.
        self._histogram.observe(self.elapsed_ms)


@dataclass
class Metrics:
    """Everything the daemon measures about itself."""

    started_at: float = field(default_factory=time.time)

    # counters
    sessions_started: int = 0
    sessions_delivered: int = 0
    sessions_cancelled: int = 0
    sessions_empty: int = 0
    faults: dict[str, int] = field(default_factory=dict)
    deliveries: dict[str, int] = field(default_factory=dict)
    device_losses: int = 0
    model_loads: int = 0
    partials_emitted: int = 0
    partials_skipped: int = 0

    # histograms
    activation_ms: Histogram = field(
        default_factory=lambda: Histogram("activation", unit="ms")
    )
    decode_ms: Histogram = field(default_factory=lambda: Histogram("decode", unit="ms"))
    partial_ms: Histogram = field(default_factory=lambda: Histogram("partial", unit="ms"))
    delivery_ms: Histogram = field(default_factory=lambda: Histogram("delivery", unit="ms"))
    end_to_end_ms: Histogram = field(
        default_factory=lambda: Histogram("end_to_end", unit="ms")
    )
    utterance_s: Histogram = field(
        default_factory=lambda: Histogram(
            "utterance", buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60, 120, 300), unit="s"
        )
    )
    confidence: Histogram = field(
        default_factory=lambda: Histogram(
            "confidence",
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            unit="score",
        )
    )

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # -- counters --------------------------------------------------------

    def count_fault(self, code: str) -> None:
        with self._lock:
            self.faults[code] = self.faults.get(code, 0) + 1

    def count_delivery(self, method: str, ok: bool) -> None:
        key = method if ok else f"{method}:failed"
        with self._lock:
            self.deliveries[key] = self.deliveries.get(key, 0) + 1

    def time(self, histogram: Histogram) -> Timer:
        return Timer(histogram)

    # -- reporting -------------------------------------------------------

    @property
    def uptime_s(self) -> float:
        return time.time() - self.started_at

    def health(self) -> tuple[str, list[str]]:
        """A blunt verdict plus the reasons for it.

        Deliberately conservative: anything that would make a user think the
        product is broken counts as degraded, even when the daemon is happily
        running.
        """
        problems: list[str] = []
        if self.sessions_started and not self.sessions_delivered:
            problems.append("no utterance has ever been delivered")
        failed = sum(v for k, v in self.deliveries.items() if k.endswith(":failed"))
        delivered = sum(v for k, v in self.deliveries.items() if not k.endswith(":failed"))
        if failed and failed >= delivered:
            problems.append(f"{failed} delivery failure(s) against {delivered} success(es)")
        if self.device_losses > 2:
            problems.append(f"the input device dropped {self.device_losses} times")
        p95 = self.end_to_end_ms.percentile(0.95)
        if self.end_to_end_ms.count >= 5 and p95 > 2000:
            problems.append(f"end-to-end p95 is {p95:.0f} ms")
        if self.faults:
            worst = max(self.faults.items(), key=lambda kv: kv[1])
            problems.append(f"{sum(self.faults.values())} fault(s), most often {worst[0]}")
        return ("degraded" if problems else "healthy"), problems

    def snapshot(self) -> dict:
        status, problems = self.health()
        with self._lock:
            faults = dict(self.faults)
            deliveries = dict(self.deliveries)
        return {
            "health": status,
            "problems": problems,
            "uptime_s": round(self.uptime_s, 1),
            "counters": {
                "sessions_started": self.sessions_started,
                "sessions_delivered": self.sessions_delivered,
                "sessions_cancelled": self.sessions_cancelled,
                "sessions_empty": self.sessions_empty,
                "device_losses": self.device_losses,
                "model_loads": self.model_loads,
                "partials_emitted": self.partials_emitted,
                "partials_skipped": self.partials_skipped,
            },
            "faults": faults,
            "deliveries": deliveries,
            "latency": {
                "activation": self.activation_ms.snapshot(),
                "partial": self.partial_ms.snapshot(),
                "decode": self.decode_ms.snapshot(),
                "delivery": self.delivery_ms.snapshot(),
                "end_to_end": self.end_to_end_ms.snapshot(),
            },
            "distribution": {
                "utterance": self.utterance_s.snapshot(),
                "confidence": self.confidence.snapshot(),
            },
        }

    def targets(self) -> list[dict]:
        """Measured percentiles against the acceptance targets in v2.md §7."""
        checks = [
            ("partial latency", self.partial_ms, 0.95, 500.0, "ms"),
            ("delivery latency", self.delivery_ms, 0.95, 700.0, "ms"),
            ("end-to-end", self.end_to_end_ms, 0.95, 1200.0, "ms"),
        ]
        out = []
        for name, histogram, fraction, budget, unit in checks:
            measured = histogram.percentile(fraction)
            out.append({
                "name": name,
                "samples": histogram.count,
                "measured": measured,
                "budget": budget,
                "unit": unit,
                # Too few samples is "unknown", never "passing". A green tick
                # from three data points is worse than no tick at all.
                "verdict": (
                    "unknown" if histogram.count < 5
                    else ("ok" if measured <= budget else "over")
                ),
            })
        return out

    def reset(self) -> None:
        with self._lock:
            self.sessions_started = self.sessions_delivered = 0
            self.sessions_cancelled = self.sessions_empty = 0
            self.device_losses = self.model_loads = 0
            self.partials_emitted = self.partials_skipped = 0
            self.faults.clear()
            self.deliveries.clear()
        for histogram in (self.activation_ms, self.decode_ms, self.partial_ms,
                          self.delivery_ms, self.end_to_end_ms,
                          self.utterance_s, self.confidence):
            histogram.reset()


def flatten(snapshot: dict, prefix: str = "dictator") -> Iterator[tuple[str, float]]:
    """Yield (name, value) pairs, for anyone wanting to scrape this."""
    for key, value in snapshot.get("counters", {}).items():
        yield f"{prefix}_{key}_total", float(value)
    for code, count in snapshot.get("faults", {}).items():
        yield f'{prefix}_faults_total{{code="{code}"}}', float(count)
    for method, count in snapshot.get("deliveries", {}).items():
        yield f'{prefix}_deliveries_total{{method="{method}"}}', float(count)
    for group in ("latency", "distribution"):
        for name, stats in snapshot.get(group, {}).items():
            for stat, value in stats.items():
                if isinstance(value, (int, float)):
                    yield f"{prefix}_{name}_{stat}", float(value)
