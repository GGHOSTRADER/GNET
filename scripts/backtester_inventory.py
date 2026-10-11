"""Read-only strategy discovery and prepared-tick catalog inspection.

Reads manifest files and Parquet footers, never tick rows. Does not merge,
repair, register, or alter archives and does not launch a backtest.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from datetime import date
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq

from strategies.registry import STRATEGIES, StrategySpec, build_strategy


DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "config/backtester.data_sources.json"


def strategy_inventory():
    rows = []
    for name, factory in sorted(STRATEGIES.items()):
        strategy = build_strategy(StrategySpec(name=name))
        parameters = getattr(strategy, "parameters", None)
        rows.append({"name": name, "implementation": factory if isinstance(factory, str)
                     else f"{factory.__module__}:{factory.__name__}",
                     "default_parameters": asdict(parameters) if is_dataclass(parameters) else None})
    return rows


def data_inventory(catalog=DEFAULT_CATALOG, asset=None, dataset=None):
    catalog = Path(catalog).resolve()
    document = json.loads(catalog.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not isinstance(document.get("datasets"), list):
        raise ValueError("expected schema_version 1 and a datasets list")
    entries = document["datasets"]
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate dataset IDs in catalog")
    selected = [entry for entry in entries if (asset is None or entry["asset"] == asset)
                and (dataset is None or entry["id"] == dataset)]
    if not selected:
        raise ValueError("no datasets match the requested asset/dataset")
    rows = []
    for entry in selected:
        root = (catalog.parent / entry["root"]).resolve()
        manifest_path = root / "manifest.json"
        errors = []
        if (root / "INCOMPLETE.txt").exists():
            errors.append("archive marked INCOMPLETE; do not use")
        manifest_hash = None
        if not manifest_path.is_file():
            errors.append("manifest missing")
        else:
            raw = manifest_path.read_bytes()
            manifest_hash = hashlib.sha256(raw).hexdigest()
            manifest = json.loads(raw)
            if manifest.get("source_timezone", entry["timezone"]) != entry["timezone"]:
                errors.append("manifest timezone differs from catalog")
            if manifest.get("symbol", entry["symbol"]) != entry["symbol"]:
                errors.append("manifest symbol differs from catalog")
        sessions = []
        for path in sorted((root / "parquet").glob("session_date=*/ticks.parquet")):
            session = path.parent.name.split("=", 1)[1]
            date.fromisoformat(session)
            parquet = pq.ParquetFile(path)
            missing = sorted({"timestamp", "price", "volume"} - set(parquet.schema_arrow.names))
            if missing:
                errors.append(f"{session}: missing columns {missing}")
            if parquet.metadata.num_rows == 0:
                errors.append(f"{session}: empty partition")
            sessions.append({"session": session, "rows": parquet.metadata.num_rows,
                             "bytes": path.stat().st_size, "path": str(path)})
        if not sessions:
            errors.append("no prepared session partitions found")
        rows.append({**entry, "root": str(root), "manifest": str(manifest_path),
                     "manifest_sha256": manifest_hash, "sessions": sessions,
                     "session_count": len(sessions), "tick_rows": sum(s["rows"] for s in sessions),
                     "first_session": sessions[0]["session"] if sessions else None,
                     "last_session": sessions[-1]["session"] if sessions else None,
                     "errors": errors})
    overlaps = []
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            if left["asset"] != right["asset"]:
                continue
            common = sorted({s["session"] for s in left["sessions"]}
                            & {s["session"] for s in right["sessions"]})
            if common:
                overlaps.append({"left": left["id"], "right": right["id"],
                                 "count": len(common), "sessions": common})
    return {"catalog": str(catalog), "datasets": rows, "overlaps": overlaps,
            "limitations": "Metadata only: dates are session labels, not proof of full sessions. "
            "Overlap is shared dates, not proof of identical ticks. Do not sum archives as unique history. "
            "No price-path, exchange-calendar completeness, or rollover alignment audit is performed."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("strategies", "data"))
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--asset")
    parser.add_argument("--dataset")
    parser.add_argument("--json", action="store_true", help="include full machine-readable partition inventory")
    args = parser.parse_args(argv)
    if args.kind == "strategies":
        result = strategy_inventory()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for row in result:
                print(f"{row['name']} -> {row['implementation']}")
                print(f"  defaults: {json.dumps(row['default_parameters'])}")
        return 0
    result = data_inventory(args.catalog, args.asset, args.dataset)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for row in result["datasets"]:
            print(f"{row['id']} | {row['asset']} | {row['status']}")
            print(f"  {row['first_session']} to {row['last_session']} | "
                  f"{row['session_count']} sessions | {row['tick_rows']:,} tick rows")
            print(f"  tick_root: {row['root']}")
            print(f"  {row['notes']}")
            for error in row["errors"]:
                print(f"  ERROR: {error}")
        for overlap in result["overlaps"]:
            print(f"OVERLAP: {overlap['left']} / {overlap['right']}: {overlap['count']} shared sessions")
        print(result["limitations"])
    return int(any(row["errors"] for row in result["datasets"]))


if __name__ == "__main__":
    raise SystemExit(main())
