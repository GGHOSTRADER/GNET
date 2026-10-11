from __future__ import annotations

import pandas as pd
import pytest

from training_mlp.merge_historical_bars import (
    HistoricalBarMergeError,
    build_session_overlap_report,
    discover_bar_exports,
    load_bar_export,
    merge_exports,
)


HEADER = "Date,Time,Open,High,Low,Close,Up,Down\n"


def _write(path, rows: list[str]) -> None:
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")


def test_discovery_keeps_base_first_and_sorts_updates(tmp_path) -> None:
    for name in (
        "data_30_update_2026-07-01_to_2026-08-01.txt",
        "data_30.txt",
        "data_30_update_2026-05-20_to_2026-07-01.txt",
    ):
        (tmp_path / name).write_text(HEADER, encoding="utf-8")

    assert [path.name for path in discover_bar_exports(tmp_path)] == [
        "data_30.txt",
        "data_30_update_2026-05-20_to_2026-07-01.txt",
        "data_30_update_2026-07-01_to_2026-08-01.txt",
    ]


def test_discovery_prefers_master_and_excludes_legacy_base(tmp_path) -> None:
    for name in (
        "data_30.txt",
        "data_30_master.txt",
        "data_30_update_2026-08-27_to_2026-09-30.txt",
    ):
        (tmp_path / name).write_text(HEADER, encoding="utf-8")

    assert [path.name for path in discover_bar_exports(tmp_path)] == [
        "data_30_master.txt",
        "data_30_update_2026-08-27_to_2026-09-30.txt",
    ]


def test_merge_removes_identical_overlap_and_sorts(tmp_path) -> None:
    base = tmp_path / "data_30.txt"
    update = tmp_path / "data_30_update_2026-05-20_to_2026-08-27.txt"
    overlap = "05/21/2026,12:27:30,5900,5901,5899,5900.5,100,80"
    _write(base, [overlap])
    _write(update, [
        overlap,
        "05/21/2026,12:28:00,5900.5,5902,5900,5901.5,110,90",
    ])

    merged, summary, conflicts = merge_exports([base, update])

    assert conflicts.empty
    assert len(merged) == 2
    assert summary["identical_duplicate_rows_removed"] == 1
    assert summary["overlapping_sessions"] == 1
    assert summary["session_overlaps"][0]["shared_timestamps"] == 1
    assert summary["session_overlaps"][0]["identical_shared_timestamps"] == 1
    assert summary["session_overlaps"][0]["conflicting_timestamps"] == 0
    assert merged["_timestamp"].is_monotonic_increasing


def test_merge_reports_different_values_at_same_timestamp(tmp_path) -> None:
    base = tmp_path / "data_30.txt"
    update = tmp_path / "data_30_update_2026-05-20_to_2026-08-27.txt"
    _write(base, ["05/21/2026,12:27:30,5900,5901,5899,5900.5,100,80"])
    _write(update, ["05/21/2026,12:27:30,5900,5901,5899,5900.75,100,80"])

    merged, summary, conflicts = merge_exports([base, update])

    assert merged.empty
    assert summary["overlapping_sessions"] == 1
    assert summary["session_overlaps"][0]["conflicting_timestamps"] == 1
    assert len(conflicts) == 2


def test_session_overlap_report_uses_1800_es_boundary(tmp_path) -> None:
    base = tmp_path / "data_30.txt"
    update = tmp_path / "data_30_update_2026-05-20_to_2026-08-27.txt"
    rows = [
        "05/20/2026,18:00:00,5900,5901,5899,5900.5,100,80",
        "05/21/2026,12:00:00,5901,5902,5900,5901.5,110,90",
    ]
    _write(base, rows)
    _write(update, rows)
    combined = pd.concat([load_bar_export(base), load_bar_export(update)])

    report = build_session_overlap_report(combined)

    assert len(report) == 1
    assert report.loc[0, "session_date"] == "2026-05-21"
    assert report.loc[0, "shared_timestamps"] == 2


def test_merge_rejects_wrong_columns(tmp_path) -> None:
    path = tmp_path / "data_30.txt"
    pd.DataFrame({"Date": ["05/21/2026"]}).to_csv(path, index=False)

    with pytest.raises(HistoricalBarMergeError, match="invalid columns"):
        merge_exports([path])
