import json

import pandas as pd
import pytest

from backtester.source_bars import HEADER, build_source_bars


def source(tmp_path, *, volume=False, boundary=False):
    path = tmp_path / "input.txt"
    rows = []
    for i in range(5):
        day = "09/30/2026"
        clock = f"09:30:{i:02d}" if not boundary else ("17:59:59" if i < 2 else "18:00:00")
        price = 6000 + i * .25
        rows.append([day, clock, price, price + (1 if volume else 0),
                     price - (.5 if volume else 0), price, i + 1, 0])
    pd.DataFrame(rows, columns=HEADER).to_csv(path, index=False)
    return path


@pytest.mark.parametrize("kind", ["tick", "volume"])
def test_construct_both_types_by_number_of_source_bars(tmp_path, kind):
    path = source(tmp_path, volume=kind == "volume")
    out = tmp_path / "out"
    result = build_source_bars(path, out, source_kind=kind, source_size=1, groups=[2, 3])
    bars = pd.read_parquet(out / f"aggregated_{kind}_src1_n2.parquet")
    assert bars["source_bar_count"].tolist() == [2, 2, 1]
    assert bars["volume"].tolist() == [3, 7, 5]  # Count rows, NOT contracts.
    assert bars["complete"].tolist() == [True, True, False]
    assert bars["open"].tolist() == [6000, 6000.5, 6001]
    assert bars["close"].tolist() == [6000.25, 6000.75, 6001]
    assert bars["high"][0] == 6000.25 + (1 if kind == "volume" else 0)
    assert bars["low"][0] == 6000 - (.5 if kind == "volume" else 0)
    assert bars["first_source_row"].tolist() == [2, 4, 6]
    assert result["source_rows"] == 5
    assert json.loads((out / "manifest.json").read_text())["operation"] == "count_source_bars"
    assert not (out / "INCOMPLETE.txt").exists()


def test_session_boundary_and_equal_timestamp_order(tmp_path):
    path = source(tmp_path, boundary=True)
    out = tmp_path / "out"
    build_source_bars(path, out, source_kind="tick", source_size=1, groups=[3])
    bars = pd.read_parquet(out / "aggregated_tick_src1_n3.parquet")
    assert bars["session"].tolist() == ["2026-09-30", "2026-10-01"]
    assert bars["source_bar_count"].tolist() == [2, 3]
    assert bars["complete"].tolist() == [False, True]
    assert bars["close"].tolist() == [6000.25, 6001]


def test_source_size_and_group_size_are_distinct(tmp_path):
    path = source(tmp_path, volume=True)
    out = tmp_path / "out"
    build_source_bars(path, out, source_kind="volume", source_size=10, groups=[2])
    assert (out / "aggregated_volume_src10_n2.parquet").exists()


def test_refuse_overwrite(tmp_path):
    path = source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(FileExistsError):
        build_source_bars(path, out, source_kind="tick", source_size=1, groups=[2])


@pytest.mark.parametrize("groups", [[], [0], [-1], [1, 1]])
def test_invalid_group_counts(tmp_path, groups):
    with pytest.raises(ValueError):
        build_source_bars(source(tmp_path), tmp_path / "out", source_kind="tick", source_size=1, groups=groups)


def test_tick_one_cannot_discard_source_ohlc_range(tmp_path):
    path = source(tmp_path, volume=True)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="equal OHLC"):
        build_source_bars(path, out, source_kind="tick", source_size=1, groups=[2])
    assert (out / "INCOMPLETE.txt").exists()
    assert not (out / "manifest.json").exists()
