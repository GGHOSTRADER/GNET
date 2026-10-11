"""Offline Parquet adapter and shared, memory-mapped tick/bar caches."""
from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from backtester.bars import aggregate
from backtester.config import Config, atomic_json, digest
from backtester.signals import generate_signals
import strategies
from strategies import build_strategy


BAR_SCHEMA = pa.schema([
    *[(n, pa.int64()) for n in ("start_ns", "end_ns", "first_event", "last_event")],
    *[(n, pa.float64()) for n in ("open", "high", "low", "close")],
    ("volume", pa.int64()), ("tick_count", pa.int64()), ("complete", pa.bool_()),
    ("session", pa.string()), ("vintage", pa.string()),
])
SIGNAL_SCHEMA = pa.schema([
    *[(n, pa.int64()) for n in ("signal_ns", "available_after_event", "entry_event", "bar_last_event", "bar_number", "signal_id", "session_index")],
])


def ns_local(value, timezone):
    return int(pd.Timestamp(value).tz_localize(timezone, ambiguous="raise", nonexistent="raise").value)


def source_inventory(config: Config):
    root = Path(config.tick_root)
    if (root / "INCOMPLETE.txt").exists():
        raise ValueError("tick archive is marked INCOMPLETE; finish or repair preparation/merge before use")
    manifest_path = root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes() if manifest_path.exists() else b"{}"
    manifest = json.loads(manifest_bytes)
    if manifest.get("source_timezone", config.timezone) != config.timezone:
        raise ValueError("source timezone differs from the configured tick timezone")
    paths = sorted((root / "parquet").glob("session_date=*/ticks.parquet"))
    old = set(manifest.get("old_sessions", []))
    new = set(manifest.get("new_sessions", []))
    sources = []
    for path in paths:
        session = path.parent.name.split("=", 1)[1]
        if not config.start_session <= session <= config.end_session:
            continue
        stat = path.stat()
        parquet = pq.ParquetFile(path)
        missing = {"timestamp", "price", "volume"} - set(parquet.schema_arrow.names)
        if missing:
            raise ValueError(f"tick partition {session} lacks required columns: {sorted(missing)}")
        sources.append({
            "path": str(path.resolve()), "session": session,
            "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "rows": parquet.metadata.num_rows,
            "vintage": "old" if session in old else "new" if session in new else root.name,
        })
    if not sources:
        raise ValueError("no tick sessions in the requested date range")
    # Prepared source partitions are immutable inputs. Stat inventory plus manifest identifies reuse.
    code_hash = hashlib.sha256()
    for namespace, package in (("backtester", Path(__file__).parent), ("strategies", Path(strategies.__file__).parent)):
        for path in sorted(package.rglob("*.py")):
            code_hash.update(f"{namespace}/{path.relative_to(package).as_posix()}".encode())
            code_hash.update(path.read_bytes())
    identity = digest({"config": config.identity(), "sources": sources,
                       "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                       "code_sha256": code_hash.hexdigest()})
    return sources, identity


def prepare(config: Config, sources, identity, progress=print):
    directory = Path(config.output) / "prepared"
    metadata_path = directory / "metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        if metadata["identity"] != identity:
            raise ValueError("prepared data identity changed; choose a new output directory")
        return metadata
    directory.mkdir(parents=True, exist_ok=True)
    total = sum(source["rows"] for source in sources)
    if total == 0:
        raise ValueError("selected tick sources contain no rows")
    arrays = {name: np.lib.format.open_memmap(directory / f"{name}.npy", mode="w+", dtype=dtype, shape=(total,))
              for name, dtype in (("times", "int64"), ("prices", "float64"), ("volumes", "int64"))}
    offset = 0
    sessions = []
    signal_counts = {spec.key: 0 for spec in config.bars}
    bar_counts = {spec.key: 0 for spec in config.bars}
    strategies = {spec.key: build_strategy(config.strategy) for spec in config.bars}
    last_vintage = None
    previous_time = None
    with ExitStack() as stack:
        writers = {}
        for spec in config.bars:
            writers[spec.key] = (
                stack.enter_context(pq.ParquetWriter(directory / f"bars_{spec.key}.parquet", BAR_SCHEMA)),
                stack.enter_context(pq.ParquetWriter(directory / f"signals_{spec.key}.parquet", SIGNAL_SCHEMA)),
            )
        for session_index, source in enumerate(sources):
            day = source["session"]
            close = config.session_close_overrides.get(day, config.session_close)
            end = ns_local(f"{day} {close}", config.timezone)
            opening_day = pd.Timestamp(day) - pd.Timedelta(days=int(config.session_open >= close))
            start = ns_local(f"{opening_day.date()} {config.session_open}", config.timezone)
            flatten = end - config.flatten_lead_seconds * 1_000_000_000
            if flatten <= start:
                raise ValueError("flatten_lead_seconds consumes an entire session")
            begin = offset
            for batch in pq.ParquetFile(source["path"]).iter_batches(batch_size=262144, columns=["timestamp", "price", "volume"]):
                table = pa.Table.from_batches([batch])
                ts = pd.DatetimeIndex(table["timestamp"].to_numpy())
                ts = ts.tz_localize(config.timezone, ambiguous="raise", nonexistent="raise") if ts.tz is None else ts
                times = ts.as_unit("ns").asi8
                prices = table["price"].to_numpy().astype(float)
                raw_volume = table["volume"].to_numpy()
                if (not np.isfinite(prices).all() or np.any(prices <= 0)
                        or not np.isfinite(raw_volume).all() or np.any(raw_volume < 0)
                        or np.any(raw_volume != np.floor(raw_volume))):
                    raise ValueError(f"invalid tick price/volume in session {day}")
                if (np.any(times[1:] < times[:-1]) or (len(times) and previous_time is not None and times[0] < previous_time)):
                    raise ValueError(f"tick order is not chronological in {day}")
                if len(times) and (times[0] < start or times[-1] >= end):
                    raise ValueError(f"ticks outside configured session hours: {day}")
                if not np.allclose(prices * 4, np.rint(prices * 4), rtol=0, atol=1e-7):
                    raise ValueError("ES prices must lie on the 0.25 tick grid")
                size = len(times)
                arrays["times"][offset:offset + size] = times
                arrays["prices"][offset:offset + size] = prices
                arrays["volumes"][offset:offset + size] = raw_volume
                offset += size
                if size:
                    previous_time = int(times[-1])
            if offset == begin:
                raise ValueError(f"empty tick session {day}")
            session = {**source, "begin": begin, "end": offset, "start_ns": start,
                       "end_ns": end, "flatten_ns": flatten}
            sessions.append(session)
            t, p, v = (arrays[name][begin:offset] for name in ("times", "prices", "volumes"))
            for spec in config.bars:
                if source["vintage"] != last_vintage:
                    strategies[spec.key] = build_strategy(config.strategy)
                strategies[spec.key].on_session_start()
                bars = aggregate(t, p, v, spec, start, end, begin)
                signals = generate_signals(bars, spec, t, begin, strategies[spec.key])
                for bar in bars:
                    bar.update(session=day, vintage=source["vintage"])
                for signal in signals:
                    signal.update(signal_id=signal_counts[spec.key], session_index=session_index)
                    signal_counts[spec.key] += 1
                bar_writer, signal_writer = writers[spec.key]
                bar_writer.write_table(pa.Table.from_pylist(bars, schema=BAR_SCHEMA))
                signal_writer.write_table(pa.Table.from_pylist(signals, schema=SIGNAL_SCHEMA))
                bar_counts[spec.key] += len(bars)
            last_vintage = source["vintage"]
            progress(f"Prepared {day}: {offset - begin:,} ticks ({session_index + 1}/{len(sources)})", flush=True)
    for array in arrays.values():
        array.flush()
    if offset != total:
        raise ValueError("source row counts changed during preparation")
    metadata = {"identity": identity, "ticks": total, "sessions": sessions,
                "bar_counts": bar_counts, "signal_counts": signal_counts,
                "timezone": config.timezone, "timestamp_storage": "UTC nanoseconds",
                "source_identity_method": "manifest SHA256 + source path/size/mtime/row count + code SHA256"}
    atomic_json(metadata_path, metadata)
    return metadata
