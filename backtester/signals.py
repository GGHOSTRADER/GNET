"""Strategy-independent completed-bar availability and next-tick entry mapping."""
import numpy as np

from strategies.base import EntryStrategy


def generate_signals(bars, spec, times, offset, strategy: EntryStrategy):
    signals = []
    for number, bar in enumerate(bars):
        if not bar["complete"] or not strategy.on_bar(bar):
            continue
        entry = (int(np.searchsorted(times, bar["end_ns"], side="left")) + offset
                 if spec.kind == "time" else bar["last_event"] + 1)
        # Time bars close before their boundary tick; tick/volume bars after their final event.
        available_after = entry - 1 if spec.kind == "time" else bar["last_event"]
        signals.append({
            "signal_ns": bar["end_ns"], "available_after_event": available_after,
            "entry_event": entry, "bar_last_event": bar["last_event"],
            "bar_number": number,
        })
    return signals
