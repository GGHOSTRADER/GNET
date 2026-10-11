from operations.live_test_monitor import _percentile, _record_event, _summary


class _Sink:
    def __init__(self):
        self.lines = []

    def write(self, value):
        self.lines.append(value)

    def flush(self):
        pass


def test_percentile_handles_empty_and_ordered_values():
    assert _percentile([], 0.95) is None
    assert _percentile([10.0, 1.0, 5.0], 0.50) == 5.0
    assert _percentile([10.0, 1.0, 5.0], 0.99) == 10.0


def test_event_counter_and_summary_track_decision_health():
    sink = _Sink()
    counters = {
        "candidates": 0,
        "decisions": 0,
        "approved": 0,
        "rejected": 0,
        "status_counts": {},
        "router_total_ms": [],
        "inference_ms": [],
    }
    _record_event(sink, "trade_candidates", "1-0", {"candidate_id": "a"}, counters)
    _record_event(
        sink,
        "trade_decisions",
        "2-0",
        {
            "candidate_id": "a",
            "status": "ok",
            "approved": "1",
            "router_total_ms": "12.5",
            "inference_ms": "0.25",
        },
        counters,
    )
    summary = _summary(
        {
            "run_id": "test",
            "started_at": "start",
            "planned_end_at": "end",
        },
        counters,
        {"redis_ok": 1},
    )
    assert summary["candidates"] == 1
    assert summary["decisions"] == 1
    assert summary["approved"] == 1
    assert summary["status_counts"] == {"ok": 1}
    assert summary["router_total_ms"]["max"] == 12.5
