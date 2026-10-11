import json
from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from training_mlp.merge_adjusted_tick_history import (
    TickVintageMergeError,
    merge_vintages,
)


def _prepared(root, sessions):
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps({
        "symbol": "@ES",
        "source_timezone": "America/New_York",
        "session_start": "18:00:00",
    }), encoding="utf-8")
    for day, price, up in sessions:
        target = root / "parquet" / f"session_date={day}" / "ticks.parquet"
        target.parent.mkdir(parents=True)
        pq.write_table(pa.table({
            "timestamp": [datetime.fromisoformat(f"{day} 09:30:00")],
            "price": [price], "up": [up], "down": [2],
        }), target)


def test_merge_shifts_only_older_sessions_and_prefers_new_overlap(tmp_path):
    old, new, output = (tmp_path / name for name in ("old", "new", "output"))
    _prepared(old, [("2026-08-12", 5000.0, 1), ("2026-08-13", 5010.0, 3)])
    _prepared(new, [("2026-08-13", 5077.75, 3), ("2026-08-14", 5080.0, 4)])

    manifest = merge_vintages(old, new, output)

    assert manifest["overlap_audit"]["ticks_checked"] == 1
    assert manifest["older_price_adjustment_points"] == 67.75
    assert manifest["output_sessions"] == 3
    first = pq.read_table(output / "parquet/session_date=2026-08-12/ticks.parquet")
    overlap = pq.read_table(output / "parquet/session_date=2026-08-13/ticks.parquet")
    assert first["price"][0].as_py() == 5067.75
    assert overlap["price"][0].as_py() == 5077.75
    assert pq.read_table(old / "parquet/session_date=2026-08-12/ticks.parquet")["price"][0].as_py() == 5000.0


def test_merge_rejects_nonmatching_overlap_without_creating_output(tmp_path):
    old, new, output = (tmp_path / name for name in ("old", "new", "output"))
    _prepared(old, [("2026-08-13", 5010.0, 3)])
    _prepared(new, [("2026-08-13", 5077.75, 4)])

    with pytest.raises(TickVintageMergeError, match="up differs"):
        merge_vintages(old, new, output)
    assert not output.exists()
