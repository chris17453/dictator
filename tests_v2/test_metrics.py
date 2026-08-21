"""Metrics, health verdicts, and the acceptance-target checks."""
import pytest

from dictatord.metrics import DEFAULT_BUCKETS, Histogram, Metrics, flatten


def test_empty_histogram_reports_nothing_rather_than_zero():
    histogram = Histogram("x")
    assert histogram.snapshot() == {"count": 0}
    assert histogram.percentile(0.95) == 0.0


def test_percentiles_are_bucket_upper_bounds():
    histogram = Histogram("x", buckets=(10, 100, 1000))
    for _ in range(90):
        histogram.observe(5)
    for _ in range(10):
        histogram.observe(900)
    assert histogram.percentile(0.5) == 10
    assert histogram.percentile(0.95) == 1000


def test_percentile_never_understates():
    """Over-reporting within a bucket is the honest direction for a budget."""
    histogram = Histogram("x", buckets=(100,))
    histogram.observe(60)
    assert histogram.percentile(0.95) >= 60


def test_values_beyond_the_last_bucket_are_counted():
    histogram = Histogram("x", buckets=(10,))
    histogram.observe(5)
    histogram.observe(10_000)
    assert histogram.count == 2
    assert histogram.snapshot()["max"] == 10_000


def test_timer_records_even_when_the_body_raises():
    metrics = Metrics()
    with pytest.raises(ValueError):
        with metrics.time(metrics.decode_ms):
            raise ValueError("boom")
    assert metrics.decode_ms.count == 1, "a fast failure must still be measured"


def test_reset_clears_everything():
    metrics = Metrics()
    metrics.sessions_started = 3
    metrics.count_fault("audio.no_device")
    metrics.decode_ms.observe(10)
    metrics.reset()
    assert metrics.sessions_started == 0
    assert metrics.faults == {}
    assert metrics.decode_ms.count == 0


# -- health ----------------------------------------------------------------


def test_a_fresh_daemon_is_healthy():
    assert Metrics().health()[0] == "healthy"


def test_sessions_that_never_deliver_are_degraded():
    metrics = Metrics()
    metrics.sessions_started = 5
    status, problems = metrics.health()
    assert status == "degraded"
    assert any("delivered" in p for p in problems)


def test_delivery_failures_outweighing_successes_are_degraded():
    metrics = Metrics()
    metrics.sessions_started = metrics.sessions_delivered = 1
    metrics.count_delivery("paste", ok=False)
    metrics.count_delivery("paste", ok=False)
    metrics.count_delivery("paste", ok=True)
    assert metrics.health()[0] == "degraded"


def test_repeated_device_loss_is_degraded():
    metrics = Metrics()
    metrics.sessions_started = metrics.sessions_delivered = 1
    metrics.device_losses = 5
    assert metrics.health()[0] == "degraded"


# -- targets ---------------------------------------------------------------


def test_too_few_samples_is_unknown_not_passing():
    """A green tick from three data points is worse than no tick at all."""
    metrics = Metrics()
    for _ in range(3):
        metrics.delivery_ms.observe(10)
    verdicts = {t["name"]: t["verdict"] for t in metrics.targets()}
    assert verdicts["delivery latency"] == "unknown"


def test_meeting_the_budget_reports_ok():
    metrics = Metrics()
    for _ in range(50):
        metrics.delivery_ms.observe(50)
    verdicts = {t["name"]: t["verdict"] for t in metrics.targets()}
    assert verdicts["delivery latency"] == "ok"


def test_exceeding_the_budget_reports_over():
    metrics = Metrics()
    for _ in range(50):
        metrics.delivery_ms.observe(5000)
    verdicts = {t["name"]: t["verdict"] for t in metrics.targets()}
    assert verdicts["delivery latency"] == "over"


def test_snapshot_is_json_serialisable():
    import json

    metrics = Metrics()
    metrics.sessions_started = 1
    metrics.count_delivery("paste", ok=True)
    metrics.count_fault("audio.no_device")
    metrics.decode_ms.observe(120)
    json.dumps(metrics.snapshot())


def test_flatten_produces_scrapeable_pairs():
    metrics = Metrics()
    metrics.sessions_started = 2
    metrics.count_fault("audio.no_device")
    pairs = dict(flatten(metrics.snapshot()))
    assert pairs["dictator_sessions_started_total"] == 2.0
    assert any("audio.no_device" in name for name in pairs)


def test_no_transcript_text_is_ever_recorded():
    """Metrics stay on the machine and must not carry what was said."""
    metrics = Metrics()
    metrics.sessions_started = 1
    metrics.count_delivery("paste", ok=True)
    blob = repr(metrics.snapshot())
    assert "text" not in blob.lower()
