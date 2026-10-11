"""Pure array aggregation; bar construction has no strategy-specific logic."""
import numpy as np

from backtester.config import BarSpec


def aggregate(times, prices, volumes, spec: BarSpec, session_start: int, session_end: int, offset: int):
    """UTC nanoseconds in; no invented empty bars. Final unconfirmed time bucket is partial."""
    if not len(times):
        return []
    if spec.kind == "time":
        width = spec.size * 1_000_000_000
        keys = (times - session_start) // width
        starts = np.r_[0, np.flatnonzero(keys[1:] != keys[:-1]) + 1]
        ends = np.r_[starts[1:], len(times)]
        begin_times = session_start + keys[starts] * width
        end_times = begin_times + width
        complete = end_times <= min(int(times[-1]), session_end)
    elif spec.kind == "tick":
        starts = np.arange(0, len(times), spec.size)
        ends = np.minimum(starts + spec.size, len(times))
        begin_times = times[starts]
        end_times = times[ends - 1]
        complete = ends - starts == spec.size
    elif spec.kind == "volume":
        # Whole-event bars: retain the threshold-crossing trade in this bar.
        # Do not split it, duplicate events or carry its overshoot into another bar.
        cumulative = np.cumsum(volumes, dtype=np.int64)
        boundaries = [0]
        completed = []
        while boundaries[-1] < len(times):
            start = boundaries[-1]
            before = int(cumulative[start - 1]) if start else 0
            last = int(np.searchsorted(cumulative, before + spec.size, side="left"))
            completed.append(last < len(times))
            boundaries.append(min(last + 1, len(times)))
        starts = np.asarray(boundaries[:-1], dtype=np.int64)
        ends = np.asarray(boundaries[1:], dtype=np.int64)
        begin_times = times[starts]
        end_times = times[ends - 1]
        complete = np.asarray(completed, dtype=bool)
    else:
        raise ValueError(f"unsupported bar kind: {spec.kind}")
    highs = np.maximum.reduceat(prices, starts)
    lows = np.minimum.reduceat(prices, starts)
    volume = np.add.reduceat(volumes, starts)
    return [{
        "start_ns": int(begin_times[i]), "end_ns": int(end_times[i]),
        "first_event": int(offset + start), "last_event": int(offset + ends[i] - 1),
        "open": float(prices[start]), "high": float(highs[i]), "low": float(lows[i]),
        "close": float(prices[ends[i] - 1]), "volume": int(volume[i]),
        "tick_count": int(ends[i] - start), "complete": bool(complete[i]),
    } for i, start in enumerate(starts)]


