import csv
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from training_mlp.prepare_historical_vp import (
    HistoricalVPError,
    discover_default_inputs,
    prepare,
    resume_preparation,
    trading_session_date,
)


HEADER = ("Date", "Time", "Open", "High", "Low", "Close", "Up", "Down")


def _write_export(path: Path, rows: list[tuple]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)


def _row(day, clock, price, up, down):
    return (day, clock, price, price, price, price, up, down)


def test_discover_default_inputs_finds_all_numbered_exports_in_numeric_order(tmp_path):
    for name in (
        "volumeprof10.txt",
        "volumeprof2.txt",
        "volumeprof1.txt",
        "volumeprof.txt",
        "volumeprof3.csv",
        "other.txt",
    ):
        (tmp_path / name).touch()

    discovered = discover_default_inputs(tmp_path)

    assert [path.name for path in discovered] == [
        "volumeprof1.txt",
        "volumeprof2.txt",
        "volumeprof10.txt",
    ]


def test_discover_default_inputs_rejects_empty_directory(tmp_path):
    with pytest.raises(HistoricalVPError, match="no inputs found"):
        discover_default_inputs(tmp_path)


def test_prepare_keeps_one_copy_of_identical_overlapping_session(tmp_path):
    first = tmp_path / "volumeprof1.txt"
    second = tmp_path / "volumeprof2.txt"
    overlap = [
        _row("07/15/2026", "18:00:00", "6000.00", 2, 0),
        _row("07/16/2026", "10:00:00", "6000.25", 0, 3),
    ]
    _write_export(first, overlap)
    _write_export(
        second,
        overlap + [_row("07/16/2026", "18:00:00", "6000.50", 1, 0)],
    )

    output = tmp_path / "prepared"
    summary = prepare([first, second], output, symbol="@ES", batch_rows=1)

    assert summary["input_rows"] == 5
    assert summary["output_sessions"] == 2
    assert summary["overlap_sessions"] == 1
    first_session = pq.read_table(
        output / "parquet" / "session_date=2026-07-16" / "ticks.parquet"
    )
    assert first_session.num_rows == 2
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    overlap_decision = manifest["partitions"][0]
    assert overlap_decision["reason"] == "identical_overlap"
    assert overlap_decision["owner"] == "volumeprof1.txt"
    assert overlap_decision["owner_parquet_bytes"] > 0


def test_prepare_can_stage_independent_sources_in_parallel(tmp_path):
    first = tmp_path / "volumeprof1.txt"
    second = tmp_path / "volumeprof2.txt"
    _write_export(first, [_row("07/15/2026", "18:00:00", "6000.00", 1, 0)])
    _write_export(second, [_row("07/16/2026", "18:00:00", "6000.25", 0, 2)])

    summary = prepare(
        [first, second],
        tmp_path / "prepared_parallel",
        symbol="@ES",
        workers=2,
    )

    assert summary["workers"] == 2
    assert summary["output_sessions"] == 2
    assert summary["staging_seconds"] >= 0
    assert summary["staging_mib_per_second"] >= 0


def test_prepare_rejects_conflicting_overlap_by_default(tmp_path):
    first = tmp_path / "volumeprof1.txt"
    second = tmp_path / "volumeprof2.txt"
    _write_export(first, [_row("07/15/2026", "18:00:00", "6000.00", 1, 0)])
    _write_export(second, [_row("07/15/2026", "18:00:00", "6000.25", 1, 0)])

    output = tmp_path / "prepared"
    with pytest.raises(HistoricalVPError, match="Staged Parquet was preserved"):
        prepare([first, second], output, symbol="@ES")

    assert (output / "staging_manifest.json").is_file()
    assert (output / "overlap_conflicts.json").is_file()
    summary = resume_preparation(output, allow_conflicting_overlaps=True)
    assert summary["status"] == "complete"
    assert not (output / ".staging").exists()
    selected = pq.ParquetFile(
        output / "parquet" / "session_date=2026-07-16" / "ticks.parquet"
    ).read()
    assert selected.column("price").to_pylist() == [6000.25]


def test_trading_session_date_rolls_at_1800():
    from datetime import date, time

    day = date(2026, 7, 15)
    assert trading_session_date(day, time(17, 59, 59)) == day
    assert trading_session_date(day, time(18, 0, 0)) == date(2026, 7, 16)
