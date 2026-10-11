"""Build an offline ES exit-outcome matrix from corrected entries and ticks.

Each entry is replayed independently under every configured three-barrier
policy. This produces research labels, not an executable portfolio backtest.
No model is trained and no live service or model registry is modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from bisect import bisect_left
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from exit_module.replay import ExitPolicy, policy_grid, replay_long, replay_long_grid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENTRIES = (
    ROOT / "training_mlp/strategies/MA2CrossLE/processed/"
    "ma2cross_corrected_jun_sep_2026.parquet"
)
DEFAULT_TICKS = ROOT / "historical_vp/prepared_spliced_2026_09_21"
DEFAULT_OUTPUT = ROOT / ".artifacts/exit_module/ma2cross_three_barrier_v2"
ROUND_TRIP_COST_USD = 6.48
BAR_SECONDS = 30
MAX_TIME_EXIT_DELAY_SECONDS = 30.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _session_date(timestamp: pd.Timestamp) -> str:
    date = timestamp.normalize()
    if timestamp.hour >= 18:
        date += pd.Timedelta(days=1)
    return date.strftime("%Y-%m-%d")


def _required_entries(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    else:
        raise ValueError("entry dataset must be a .parquet or .csv file")
    if "candidate_time" not in frame and "feature_time" in frame:
        frame["candidate_time"] = frame["feature_time"]
    needed = {
        "trade_number", "vintage", "candidate_time", "entry_time",
        "exit_time", "entry_price", "exit_price", "exit_signal",
        "net_pnl_at_3_24_per_side",
    }
    missing = needed - set(frame.columns)
    if missing:
        raise ValueError(f"entry dataset lacks columns: {sorted(missing)}")
    if frame.empty or frame.duplicated(["vintage", "trade_number"]).any():
        raise ValueError("entry dataset is empty or has duplicate vintage/trade keys")
    for field in ("candidate_time", "entry_time", "exit_time"):
        frame[field] = pd.to_datetime(frame[field], errors="raise")
        if frame[field].isna().any():
            raise ValueError(f"entry dataset has null {field}")
    if (frame["candidate_time"] >= frame["entry_time"]).any():
        raise ValueError("candidate timestamps must precede entry-bar timestamps")
    if (frame["exit_time"] < frame["entry_time"]).any():
        raise ValueError("recorded exits precede their entry bars")
    if not np.isfinite(frame[["entry_price", "exit_price"]].to_numpy(dtype=float)).all():
        raise ValueError("entry dataset has non-finite prices")
    frame = frame.sort_values(["entry_time", "vintage", "trade_number"], kind="stable")
    frame = frame.reset_index(drop=True)
    frame["entry_market_time"] = frame["entry_time"] - pd.Timedelta(seconds=BAR_SECONDS)
    if (frame["candidate_time"] > frame["entry_market_time"]).any():
        raise ValueError("a candidate occurs after its entry bar begins")
    frame["entry_session"] = frame["entry_market_time"].map(_session_date)
    return frame


class TickStore:
    """Bounded-memory reader of unadjusted, session-partitioned ES ticks."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self.paths = {
            path.parent.name.removeprefix("session_date="): path
            for path in (self.root / "parquet").glob("session_date=*/ticks.parquet")
        }
        if not self.paths:
            raise FileNotFoundError(f"no tick partitions under {self.root}")
        self.sessions = sorted(self.paths)

    @lru_cache(maxsize=3)
    def _load(self, session: str) -> tuple[np.ndarray, np.ndarray]:
        table = pq.ParquetFile(self.paths[session]).read(columns=["timestamp", "price"])
        times = table["timestamp"].to_numpy().astype("datetime64[ns]")
        prices = table["price"].to_numpy().astype(np.float64)
        if len(times) == 0 or np.any(times[1:] < times[:-1]):
            raise ValueError(f"tick partition is empty or unsorted: {session}")
        if not np.isfinite(prices).all() or np.any(prices <= 0):
            raise ValueError(f"tick partition has invalid prices: {session}")
        return times, prices

    def window(
        self, start: pd.Timestamp, through: pd.Timestamp
    ) -> tuple[np.ndarray, np.ndarray, bool]:
        """Read from start through the first tick at/after through.

        The first tick after a deadline is necessary to price a time-market
        exit. It may be delayed by a market closure; that delay is recorded.
        """
        if through < start:
            raise ValueError("tick window endpoint precedes entry")
        session = _session_date(start)
        if session not in self.paths:
            raise FileNotFoundError(f"missing entry tick session: {session}")
        position = bisect_left(self.sessions, session)
        pieces_t: list[np.ndarray] = []
        pieces_p: list[np.ndarray] = []
        start64 = np.datetime64(start, "ns")
        end64 = np.datetime64(through, "ns")
        reached_end = False
        for name in self.sessions[position:]:
            times, prices = self._load(name)
            left = int(np.searchsorted(times, start64, side="left"))
            if left == len(times):
                continue
            first_at_end = int(np.searchsorted(times, end64, side="left"))
            right = min(len(times), max(left, first_at_end) + 1)
            if right > left:
                pieces_t.append(times[left:right])
                pieces_p.append(prices[left:right])
            if first_at_end < len(times):
                reached_end = True
                break
        if not pieces_t:
            return np.array([], dtype="datetime64[ns]"), np.array([], dtype=float), False
        return np.concatenate(pieces_t), np.concatenate(pieces_p), reached_end


def _audit_row(
    trade: object,
    ticks: TickStore,
    *,
    cost: float,
    include_entry_timestamp: bool,
) -> dict[str, object]:
    start = trade.entry_market_time
    times, prices, _ = ticks.window(start, trade.exit_time)
    baseline = replay_long(
        times, prices, entry_time=np.datetime64(start, "ns"),
        entry_price=float(trade.entry_price),
        policy=ExitPolicy(4, 4, None), round_trip_cost_usd=cost,
        include_entry_timestamp=include_entry_timestamp,
    )
    observed_reason = {"Profit Target": "profit", "Stop Loss": "loss"}.get(
        trade.exit_signal
    )
    if observed_reason is None:
        raise ValueError(f"unsupported recorded exit: {trade.exit_signal}")
    matched = (
        baseline.reason == observed_reason
        and baseline.net_pnl_usd is not None
        and abs(baseline.net_pnl_usd - trade.net_pnl_at_3_24_per_side) < 0.011
        and baseline.timestamp is not None
        and baseline.timestamp <= np.datetime64(trade.exit_time, "ns")
    )
    first_index = int(np.searchsorted(
        times, np.datetime64(start, "ns"),
        side="left" if include_entry_timestamp else "right",
    ))
    first_tick_price = float(prices[first_index]) if first_index < len(prices) else None
    return {
        "vintage": trade.vintage,
        "trade_number": int(trade.trade_number),
        "entry_market_time": start,
        "recorded_exit_bar_time": trade.exit_time,
        "recorded_reason": observed_reason,
        "recorded_net_pnl_usd": float(trade.net_pnl_at_3_24_per_side),
        "replay_reason": baseline.reason,
        "replay_exit_time": baseline.timestamp,
        "replay_net_pnl_usd": baseline.net_pnl_usd,
        "first_tick_price": first_tick_price,
        "first_tick_gap_ticks": (
            None if first_tick_price is None
            else (first_tick_price - float(trade.entry_price)) / 0.25
        ),
        "matched": bool(matched),
    }


def collect_exit_data(
    entries_path: Path,
    tick_root: Path,
    output_root: Path,
    *,
    profits: tuple[int, ...],
    stops: tuple[int, ...],
    hold_seconds: tuple[int, ...],
    round_trip_cost_usd: float = ROUND_TRIP_COST_USD,
    include_entry_timestamp: bool = True,
    max_time_exit_delay_seconds: float = MAX_TIME_EXIT_DELAY_SECONDS,
    max_trades: int | None = None,
) -> dict[str, object]:
    """Write a new long-form outcome dataset without changing any source."""
    policies = policy_grid(profits, stops, hold_seconds)
    if not np.isfinite(max_time_exit_delay_seconds) or max_time_exit_delay_seconds < 0:
        raise ValueError("maximum time-exit delay must be finite and nonnegative")
    if max_trades is not None and max_trades < 1:
        raise ValueError("max_trades must be positive")
    entries_path = entries_path.resolve(strict=True)
    tick_root = tick_root.resolve(strict=True)
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"output already exists: {output_root}")
    entries = _required_entries(entries_path)
    if max_trades is not None:
        entries = entries.head(max_trades).copy()
    tick_store = TickStore(tick_root)
    source_manifest = tick_root / "manifest.json"

    output_root.mkdir(parents=True)
    marker = output_root / "INCOMPLETE.txt"
    marker.write_text("Collection has not completed; do not train on this output.\n", encoding="utf-8")
    try:
        entries.to_parquet(output_root / "entries.parquet", index=False)
        audit_rows: list[dict[str, object]] = []
        summaries: dict[str, dict[str, float | int]] = {
            policy.policy_id: {"profit": 0, "loss": 0, "time": 0,
                               "unavailable_time": 0, "censored": 0,
                               "net_pnl_usd": 0.0}
            for policy in policies
        }
        for session, group in entries.groupby("entry_session", sort=True):
            rows: list[dict[str, object]] = []
            for trade in group.itertuples(index=False):
                audit = _audit_row(
                    trade, tick_store, cost=round_trip_cost_usd,
                    include_entry_timestamp=include_entry_timestamp,
                )
                audit_rows.append(audit)
                start = trade.entry_market_time
                deadline = start + timedelta(seconds=max(hold_seconds))
                times, prices, covered = tick_store.window(start, deadline)
                results = replay_long_grid(
                    times, prices, entry_time=np.datetime64(start, "ns"),
                    entry_price=float(trade.entry_price), policies=policies,
                    round_trip_cost_usd=round_trip_cost_usd,
                    include_entry_timestamp=include_entry_timestamp,
                    max_time_exit_delay_seconds=max_time_exit_delay_seconds,
                )
                for policy, result in zip(policies, results, strict=True):
                    if result.reason == "censored" and covered:
                        raise RuntimeError(
                            f"replay censored despite tick coverage: {session} "
                            f"trade {trade.trade_number} {policy.policy_id}"
                        )
                    summary = summaries[policy.policy_id]
                    summary[result.reason] = int(summary[result.reason]) + 1
                    if result.net_pnl_usd is not None:
                        summary["net_pnl_usd"] = float(summary["net_pnl_usd"]) + result.net_pnl_usd
                    rows.append({
                        "vintage": trade.vintage,
                        "trade_number": int(trade.trade_number),
                        "candidate_time": trade.candidate_time,
                        "entry_market_time": start,
                        "entry_bar_end_time": trade.entry_time,
                        "entry_price": float(trade.entry_price),
                        "policy_id": policy.policy_id,
                        "profit_ticks": policy.profit_ticks,
                        "stop_ticks": policy.stop_ticks,
                        "max_hold_seconds": policy.max_hold_seconds,
                        "exit_reason": result.reason,
                        "exit_tick_time": result.timestamp,
                        "exit_price": result.exit_price,
                        "gross_pnl_usd": result.gross_pnl_usd,
                        "net_pnl_usd": result.net_pnl_usd,
                        "time_exit_delay_seconds": result.time_exit_delay_seconds,
                        "baseline_replay_matched": audit["matched"],
                    })
            partition = output_root / "outcomes" / f"entry_session={session}"
            partition.mkdir(parents=True)
            pd.DataFrame(rows).to_parquet(partition / "outcomes.parquet", index=False)

        audit_frame = pd.DataFrame(audit_rows)
        audit_frame.to_parquet(output_root / "baseline_audit.parquet", index=False)
        summary_frame = pd.DataFrame([
            {"policy_id": key, **value} for key, value in summaries.items()
        ])
        summary_frame.to_csv(output_root / "descriptive_summary.csv", index=False)
        matched = int(audit_frame["matched"].sum())
        censored = int(summary_frame["censored"].sum())
        unavailable_time = int(summary_frame["unavailable_time"].sum())
        manifest: dict[str, object] = {
            "schema_version": 1,
            "research_only": True,
            "dataset_ready_for_training": (
                matched == len(entries) and censored == 0 and unavailable_time == 0
            ),
            "entry_source": str(entries_path),
            "entry_source_sha256": _sha256(entries_path),
            "tick_source": str(tick_root),
            "tick_manifest_sha256": (
                _sha256(source_manifest) if source_manifest.exists() else None
            ),
            "entries": int(len(entries)),
            "policies": len(policies),
            "outcome_rows": int(len(entries) * len(policies)),
            "baseline_4tick_matches": matched,
            "baseline_4tick_mismatches": int(len(entries) - matched),
            "censored_policy_rows": censored,
            "unavailable_time_policy_rows": unavailable_time,
            "round_trip_cost_usd": round_trip_cost_usd,
            "max_time_exit_delay_seconds": max_time_exit_delay_seconds,
            "entry_boundary": "inclusive" if include_entry_timestamp else "exclusive",
            "entry_market_time_rule": "TradeStation entry bar end minus 30 seconds",
            "time_barrier_rule": (
                "first observed tick at or after deadline; time wins ties; "
                "delay above configured limit has no assigned P&L"
            ),
            "price_fill_rule": "target at limit, stop at first observed crossing price, time at first tick",
            "profit_ticks": list(sorted(set(profits))),
            "stop_ticks": list(sorted(set(stops))),
            "hold_seconds": list(sorted(set(hold_seconds))),
            "independent_counterfactuals": True,
            "portfolio_overlap_not_resolved": True,
            "no_model_trained": True,
            "live_pipeline_unchanged": True,
        }
        (output_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        marker.unlink()
        return manifest
    except Exception:
        raise


def _positive_ints(raw: str) -> tuple[int, ...]:
    try:
        values = tuple(int(value.strip()) for value in raw.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from error
    if not values or any(value < 1 for value in values):
        raise argparse.ArgumentTypeError("all grid values must be positive integers")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries", type=Path, default=DEFAULT_ENTRIES)
    parser.add_argument("--ticks", type=Path, default=DEFAULT_TICKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--profits", type=_positive_ints, default=(1, 2, 3, 4, 6, 8))
    parser.add_argument("--stops", type=_positive_ints, default=(1, 2, 3, 4, 6, 8))
    parser.add_argument("--times", type=_positive_ints, default=(30, 60, 120, 300))
    parser.add_argument("--max-trades", type=int, default=None)
    parser.add_argument(
        "--max-time-exit-delay-seconds", type=float,
        default=MAX_TIME_EXIT_DELAY_SECONDS,
    )
    parser.add_argument("--exclude-entry-timestamp", action="store_true")
    args = parser.parse_args()
    result = collect_exit_data(
        args.entries, args.ticks, args.output,
        profits=args.profits, stops=args.stops, hold_seconds=args.times,
        include_entry_timestamp=not args.exclude_entry_timestamp,
        max_time_exit_delay_seconds=args.max_time_exit_delay_seconds,
        max_trades=args.max_trades,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
