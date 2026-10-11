"""Research-only comparison: adjust two prepared @ES tick vintages.

The newer export owns overlapping sessions. Older-only session prices are
shifted by the offset measured from every overlapping tick. Raw files and
existing prepared datasets are never modified. This output is not the selected
paired bar/tick history; use splice_historical_vintages for that history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


class TickVintageMergeError(ValueError):
    """Raised when two prepared vintages cannot be joined safely."""


def _partitions(root: Path) -> dict[str, Path]:
    paths = {p.parent.name.removeprefix("session_date="): p
             for p in (root / "parquet").glob("session_date=*/ticks.parquet")}
    if not paths:
        raise TickVintageMergeError(f"no tick partitions under {root}")
    return paths


def _manifest(root: Path) -> tuple[dict, str]:
    path = root / "manifest.json"
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def audit_overlap(old: dict[str, Path], new: dict[str, Path]) -> dict:
    overlap = sorted(old.keys() & new.keys())
    if not overlap:
        raise TickVintageMergeError("no overlapping sessions to measure a price adjustment")
    offset: float | None = None
    checked = 0
    for session in overlap:
        columns = ["timestamp", "price", "up", "down"]
        # Read the file schema only; Hive discovery would infer session_date
        # from the parent directory and conflict with the stored date32 field.
        left = pq.ParquetFile(old[session]).read(columns=columns)
        right = pq.ParquetFile(new[session]).read(columns=columns)
        if left.num_rows != right.num_rows:
            raise TickVintageMergeError(f"{session}: tick counts differ")
        for column in ("timestamp", "up", "down"):
            if not np.array_equal(left[column].to_numpy(), right[column].to_numpy()):
                raise TickVintageMergeError(f"{session}: {column} differs between vintages")
        differences = right["price"].to_numpy() - left["price"].to_numpy()
        if not np.isfinite(differences).all():
            raise TickVintageMergeError(f"{session}: non-finite price difference")
        if offset is None:
            offset = float(differences[0])
        if not np.allclose(differences, offset, atol=1e-9, rtol=0):
            raise TickVintageMergeError(f"{session}: price offset is not constant")
        checked += left.num_rows
    assert offset is not None
    if not np.isclose(offset * 4, round(offset * 4), atol=1e-9):
        raise TickVintageMergeError(f"price offset {offset} is not an ES tick multiple")
    return {"sessions": overlap, "ticks_checked": checked, "new_minus_old_points": offset}


def merge_vintages(old_root: Path, new_root: Path, output_root: Path) -> dict:
    """Write a new partitioned dataset; never overwrite either input."""
    old_root = old_root.resolve(strict=True)
    new_root = new_root.resolve(strict=True)
    output_root = output_root.resolve()
    if output_root.exists():
        raise TickVintageMergeError(f"output already exists: {output_root}")
    old_manifest, old_hash = _manifest(old_root)
    new_manifest, new_hash = _manifest(new_root)
    for field in ("symbol", "source_timezone", "session_start"):
        if old_manifest.get(field) != new_manifest.get(field):
            raise TickVintageMergeError(f"prepared datasets disagree on {field}")
    old = _partitions(old_root)
    new = _partitions(new_root)
    audit = audit_overlap(old, new)
    offset = audit["new_minus_old_points"]
    old_only = sorted(old.keys() - new.keys())
    if old_only and max(old_only) >= min(new):
        raise TickVintageMergeError("old-only sessions extend into new coverage")
    session_ids = sorted(old.keys() | new.keys())

    output_root.mkdir(parents=True)
    parquet_root = output_root / "parquet"
    parquet_root.mkdir()
    try:
        for session in session_ids:
            destination = parquet_root / f"session_date={session}" / "ticks.parquet"
            destination.parent.mkdir()
            if session in new:
                shutil.copy2(new[session], destination)
            else:
                table = pq.ParquetFile(old[session]).read()
                price_index = table.schema.get_field_index("price")
                adjusted = pc.add(table["price"], pa.scalar(offset, type=pa.float64()))
                table = table.set_column(price_index, "price", adjusted)
                pq.write_table(table, destination, compression="zstd")
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now().astimezone().isoformat(),
            "symbol": new_manifest["symbol"],
            "source_timezone": new_manifest["source_timezone"],
            "session_start": new_manifest["session_start"],
            "old_prepared_root": str(old_root),
            "old_manifest_sha256": old_hash,
            "new_prepared_root": str(new_root),
            "new_manifest_sha256": new_hash,
            "older_price_adjustment_points": offset,
            "overlap_audit": audit,
            "older_adjusted_sessions": old_only,
            "newer_owned_sessions": sorted(new),
            "output_sessions": len(session_ids),
            "first_session": session_ids[0],
            "last_session": session_ids[-1],
        }
        (output_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    except Exception:
        (output_root / "INCOMPLETE.txt").write_text(
            "Do not use this output; merge did not complete.\n", encoding="utf-8"
        )
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, default=Path("historical_vp/prepared"))
    parser.add_argument("--new", type=Path, default=Path("historical_vp/prepared_new_2026_09_21"))
    parser.add_argument("--output", type=Path, default=Path("historical_vp/prepared_continuous_2026_09_21"))
    args = parser.parse_args()
    manifest = merge_vintages(args.old, args.new, args.output)
    print(json.dumps({k: manifest[k] for k in (
        "overlap_audit", "output_sessions", "first_session", "last_session"
    )}, indent=2))


if __name__ == "__main__":
    main()
