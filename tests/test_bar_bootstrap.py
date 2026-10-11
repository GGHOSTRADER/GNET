from __future__ import annotations

from netwo_files.bar_codec import (
    BAR_MODE_BOOTSTRAP,
    BAR_MODE_BOOTSTRAP_END,
    BAR_MODE_LIVE,
    bar_to_redis_fields,
    parse_bar_wire_line,
)
from netwo_files.bar_contract import Bar
from feat_files import transformer_features


LEGACY_LINE = "@ES,1260918,34200,6800,6801,6799,6800.5,10,5,6800.25,61"


def test_legacy_bar_wire_line_is_live() -> None:
    mode, bar = parse_bar_wire_line(LEGACY_LINE)
    assert mode == BAR_MODE_LIVE
    assert bar.time_s == 34200


def test_mode_prefixed_bootstrap_lines() -> None:
    mode, bar = parse_bar_wire_line("1," + LEGACY_LINE)
    assert mode == BAR_MODE_BOOTSTRAP
    assert bar.symbol == "@ES"

    mode, bar = parse_bar_wire_line("2," + LEGACY_LINE)
    assert mode == BAR_MODE_BOOTSTRAP_END
    assert bar.bar_num == 61


def test_redis_fields_retain_bootstrap_boundary() -> None:
    _, bar = parse_bar_wire_line("2," + LEGACY_LINE)
    fields = bar_to_redis_fields(bar, ingest_mode=BAR_MODE_BOOTSTRAP_END)
    assert fields["ingest_mode"] == BAR_MODE_BOOTSTRAP_END


def _bar(index: int, *, base_time: int = 34200) -> Bar:
    return Bar(
        symbol="@ES",
        date=1260918,
        time_s=base_time + index * 30,
        open=6800.0,
        high=6801.0,
        low=6799.0,
        close=6800.5,
        up=10 + index,
        down=5,
        vwap=6800.25,
        bar_num=index + 1,
    )


def test_bootstrap_boundary_discards_partial_live_window(monkeypatch) -> None:
    events = [(BAR_MODE_LIVE, _bar(index)) for index in range(10)]
    events.extend(
        (BAR_MODE_BOOTSTRAP_END if index == 59 else BAR_MODE_BOOTSTRAP, _bar(index, base_time=36000))
        for index in range(60)
    )

    monkeypatch.setattr(
        transformer_features,
        "stream_bars_from_redis",
        lambda **_kwargs: iter(events),
    )

    points = list(transformer_features.stream_feature_points())
    assert len(points) == 1
    assert points[0].time_s == 36000 + 59 * 30
    assert points[0].bar_num == 60
