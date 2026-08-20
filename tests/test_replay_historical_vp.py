from datetime import date, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from training_mlp.replay_historical_vp import (
    discover_session_parquets,
    replay_session,
)


def _write_ticks(path):
    calendar_day = date(2026, 8, 18)
    rows = [
        (datetime(2026, 8, 18, 10, 0, 0), 36000, 5000.00, 1, 0),
        (datetime(2026, 8, 18, 10, 0, 29, 100000), 36029, 5000.00, 2, 0),
        (datetime(2026, 8, 18, 10, 0, 29, 900000), 36029, 5000.25, 0, 1),
        (datetime(2026, 8, 18, 10, 0, 30), 36030, 5000.25, 1, 0),
        (datetime(2026, 8, 18, 10, 0, 59, 100000), 36059, 5000.25, 3, 0),
        (datetime(2026, 8, 18, 10, 0, 59, 900000), 36059, 5000.00, 0, 1),
    ]
    table = pa.table(
        {
            "timestamp": [row[0] for row in rows],
            "calendar_date": [calendar_day] * len(rows),
            "session_date": [calendar_day] * len(rows),
            "time_s": [row[1] for row in rows],
            "price": [row[2] for row in rows],
            "up": [row[3] for row in rows],
            "down": [row[4] for row in rows],
            "volume": [row[3] + row[4] for row in rows],
            "source_file": ["volumeprof1.txt"] * len(rows),
            "source_row": list(range(1, len(rows) + 1)),
        }
    )
    path.parent.mkdir(parents=True)
    pq.write_table(table, path)


def test_replay_keeps_freshest_final_second_tick_and_commits_once(tmp_path):
    input_path = (
        tmp_path / "prepared" / "session_date=2026-08-18" / "ticks.parquet"
    )
    output_path = (
        tmp_path / "features" / "session_date=2026-08-18" / "vp_features.parquet"
    )
    _write_ticks(input_path)

    summary = replay_session(
        input_path,
        output_path,
        range_ticks=20,
        batch_rows=2,
    )
    rows = pq.read_table(output_path).to_pylist()

    assert summary["input_rows"] == 6
    assert summary["feature_rows"] == 2
    assert [row["time_s"] for row in rows] == [36029, 36059]
    assert rows[0]["snapshot_timestamp"] == datetime(
        2026, 8, 18, 10, 0, 29, 900000
    )
    assert rows[1]["snapshot_timestamp"] == datetime(
        2026, 8, 18, 10, 0, 59, 900000
    )
    assert rows[0]["total_volume"] == pytest.approx(4.0)
    assert rows[1]["total_volume"] == pytest.approx(9.0)
    assert rows[1]["recent_classified_delta_ratio"] == pytest.approx(0.6)


def test_discover_session_parquets_returns_chronological_partitions(tmp_path):
    later = tmp_path / "session_date=2026-08-19" / "ticks.parquet"
    earlier = tmp_path / "session_date=2026-08-18" / "ticks.parquet"
    _write_ticks(later)
    _write_ticks(earlier)

    assert discover_session_parquets(tmp_path) == [earlier, later]
