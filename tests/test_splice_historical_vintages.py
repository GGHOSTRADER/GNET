import json
from datetime import datetime

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from training_mlp.splice_historical_vintages import VintageSpliceError, splice_vintages


def _bars(path, day, price):
    pd.DataFrame([{
        "Date": day, "Time": "18:00:30", "Open": price, "High": price,
        "Low": price, "Close": price, "Up": 1, "Down": 2,
    }]).to_csv(path, index=False)


def _ticks(root, session, price):
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps({
        "symbol": "@ES", "source_timezone": "America/New_York",
        "session_start": "18:00:00",
    }), encoding="utf-8")
    path = root / "parquet" / f"session_date={session}" / "ticks.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(pa.table({
        "timestamp": [datetime.fromisoformat("2026-08-13 18:00:00")],
        "price": [price], "up": [1], "down": [2],
    }), path)


def test_splice_keeps_each_vintage_unadjusted_and_paired(tmp_path):
    old_bar, new_bar = tmp_path / "old.csv", tmp_path / "new.csv"
    old_tick, new_tick = tmp_path / "old", tmp_path / "new"
    output_bar, output_tick = tmp_path / "spliced.csv", tmp_path / "spliced"
    _bars(old_bar, "08/13/2026", 5000.0)
    _bars(new_bar, "08/16/2026", 5075.0)
    _ticks(old_tick, "2026-08-14", 5000.0)
    _ticks(new_tick, "2026-08-17", 5075.0)

    manifest = splice_vintages(
        old_bar, new_bar, old_tick, new_tick, output_bar, output_tick,
        cutoff_session="2026-08-14",
    )

    assert manifest["first_new_session"] == "2026-08-17"
    assert manifest["price_adjustment_applied"] is False
    assert pd.read_csv(output_bar)["Close"].tolist() == [5000.0, 5075.0]
    assert pq.read_table(output_tick / "parquet/session_date=2026-08-14/ticks.parquet")["price"][0].as_py() == 5000.0
    assert pq.read_table(output_tick / "parquet/session_date=2026-08-17/ticks.parquet")["price"][0].as_py() == 5075.0


def test_splice_rejects_missing_tick_session_before_writing(tmp_path):
    old_bar, new_bar = tmp_path / "old.csv", tmp_path / "new.csv"
    old_tick, new_tick = tmp_path / "old", tmp_path / "new"
    _bars(old_bar, "08/13/2026", 5000.0)
    _bars(new_bar, "08/16/2026", 5075.0)
    _ticks(old_tick, "2026-08-14", 5000.0)
    _ticks(new_tick, "2026-08-18", 5075.0)

    with pytest.raises(VintageSpliceError, match="bar/tick sessions differ"):
        splice_vintages(
            old_bar, new_bar, old_tick, new_tick,
            tmp_path / "out.csv", tmp_path / "out",
            cutoff_session="2026-08-14",
        )
    assert not (tmp_path / "out").exists()
