"""Splice old bars/ticks through a shared ES session, then new bars/ticks.

No prices, volumes, timestamps, or raw inputs are modified. Both streams use
the same source vintage for every session. The handoff is a price-scale break,
not an adjusted continuous series; feature state must reset at that boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from training_mlp.merge_historical_bars import REQUIRED_COLUMNS, load_bar_export


class VintageSpliceError(ValueError):
    """Raised when the old/new bar and tick coverage cannot be spliced safely."""


def _manifest(root: Path) -> tuple[dict, str]:
    raw = (root / "manifest.json").read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _ticks(root: Path) -> dict[str, Path]:
    found = {
        path.parent.name.removeprefix("session_date="): path
        for path in (root / "parquet").glob("session_date=*/ticks.parquet")
    }
    if not found:
        raise VintageSpliceError(f"no prepared ticks under {root}")
    return found


def splice_vintages(
    old_bars_path: Path,
    new_bars_path: Path,
    old_ticks_root: Path,
    new_ticks_root: Path,
    output_bars_path: Path,
    output_ticks_root: Path,
    *,
    cutoff_session: str,
) -> dict:
    """Write a new paired history without altering either source vintage."""
    date.fromisoformat(cutoff_session)
    if output_bars_path.exists() or output_ticks_root.exists():
        raise VintageSpliceError("refusing to overwrite a bar or tick output")
    old_bar = load_bar_export(old_bars_path)
    new_bar = load_bar_export(new_bars_path)
    old_tick = _ticks(old_ticks_root)
    new_tick = _ticks(new_ticks_root)
    old_tick_manifest, old_tick_hash = _manifest(old_ticks_root)
    new_tick_manifest, new_tick_hash = _manifest(new_ticks_root)
    for key in ("symbol", "source_timezone", "session_start"):
        if old_tick_manifest.get(key) != new_tick_manifest.get(key):
            raise VintageSpliceError(f"tick vintages disagree on {key}")

    old_bar = old_bar.loc[old_bar["_session_date"] <= cutoff_session]
    new_bar = new_bar.loc[new_bar["_session_date"] > cutoff_session]
    bars = pd.concat([old_bar, new_bar], ignore_index=True)
    bars = bars.sort_values("_timestamp", kind="stable").reset_index(drop=True)
    if bars.empty or bars["_timestamp"].duplicated().any():
        raise VintageSpliceError("spliced bars are empty or contain duplicate timestamps")

    selected_ticks = {
        **{day: path for day, path in old_tick.items() if day <= cutoff_session},
        **{day: path for day, path in new_tick.items() if day > cutoff_session},
    }
    bar_sessions = set(bars["_session_date"])
    if bar_sessions != set(selected_ticks):
        missing_ticks = sorted(bar_sessions - set(selected_ticks))
        missing_bars = sorted(set(selected_ticks) - bar_sessions)
        raise VintageSpliceError(
            f"bar/tick sessions differ: missing ticks={missing_ticks}, "
            f"missing bars={missing_bars}"
        )
    if cutoff_session not in old_tick or cutoff_session not in set(old_bar["_session_date"]):
        raise VintageSpliceError("cutoff session is absent from an old source")
    old_days = sorted(day for day in selected_ticks if day <= cutoff_session)
    new_days = sorted(day for day in selected_ticks if day > cutoff_session)
    if not new_days:
        raise VintageSpliceError("no new sessions follow the cutoff")

    output_ticks_root.mkdir(parents=True)
    try:
        for day, source in sorted(selected_ticks.items()):
            target = output_ticks_root / "parquet" / f"session_date={day}" / "ticks.parquet"
            target.parent.mkdir(parents=True)
            shutil.copy2(source, target)
        output_bars_path.parent.mkdir(parents=True, exist_ok=True)
        bars.loc[:, list(REQUIRED_COLUMNS)].to_csv(output_bars_path, index=False)
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now().astimezone().isoformat(),
            "cutoff_session": cutoff_session,
            "first_new_session": new_days[0],
            "price_adjustment_applied": False,
            "feature_reset_required_at_handoff": True,
            "old_bar_source": str(old_bars_path.resolve()),
            "new_bar_source": str(new_bars_path.resolve()),
            "old_tick_prepared": str(old_ticks_root.resolve()),
            "old_tick_manifest_sha256": old_tick_hash,
            "new_tick_prepared": str(new_ticks_root.resolve()),
            "new_tick_manifest_sha256": new_tick_hash,
            "output_bar_path": str(output_bars_path.resolve()),
            "output_bar_rows": len(bars),
            "output_tick_sessions": len(selected_ticks),
            "output_tick_rows": sum(pq.ParquetFile(path).metadata.num_rows
                                    for path in selected_ticks.values()),
            "old_sessions": old_days,
            "new_sessions": new_days,
        }
        (output_ticks_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        output_bars_path.with_suffix(".manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except Exception:
        (output_ticks_root / "INCOMPLETE.txt").write_text(
            "Do not use: vintage splice did not complete.\n", encoding="utf-8"
        )
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = Path("training_mlp/strategies/MA2CrossLE/inputs")
    parser.add_argument("--old-bars", type=Path, default=inputs / "data_30_master.txt")
    parser.add_argument("--new-bars", type=Path,
                        default=inputs / "data_30_update_2026-03-23_to_2026-09-21.txt")
    parser.add_argument("--old-ticks", type=Path, default=Path("historical_vp/prepared"))
    parser.add_argument("--new-ticks", type=Path,
                        default=Path("historical_vp/prepared_new_2026_09_21"))
    parser.add_argument("--output-bars", type=Path,
                        default=inputs / "data_30_spliced_2026-09-21.txt")
    parser.add_argument("--output-ticks", type=Path,
                        default=Path("historical_vp/prepared_spliced_2026_09_21"))
    parser.add_argument("--cutoff-session", default="2026-08-14")
    args = parser.parse_args()
    result = splice_vintages(
        args.old_bars, args.new_bars, args.old_ticks, args.new_ticks,
        args.output_bars, args.output_ticks, cutoff_session=args.cutoff_session,
    )
    print(json.dumps({key: result[key] for key in (
        "cutoff_session", "first_new_session", "output_bar_rows",
        "output_tick_sessions", "output_tick_rows",
    )}, indent=2))


if __name__ == "__main__":
    main()
