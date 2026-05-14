"""
consolidator.py
===============

Consolidates features_transformer and features_volume_profile into a single
merged feature print per bar.

Flow
----
1. Block on features_transformer (bottleneck — fires once per bar)
2. On new entry: grab latest features_volume_profile (non-blocking)
3. Validate both entries share the same symbol
4. Print merged feature set

Design decisions
----------------
- features_transformer is the clock: nothing prints until a new bar arrives
- features_volume_profile is grabbed as latest available (xrevrange count=1)
- If VP stream has no data: prints TF features + "NO features for volume"
- If symbols mismatch: logs warning and skips (does not print)

Function Summary
----------------
1) _print_consolidated(tf, vp)  -- formats and prints merged features to stdout
2) main()                       -- main loop: xread TF -> xrevrange VP -> validate -> print

Run
---
python -m feat_files.consolidator
"""

from config.setting import (
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_FEATURES_TRANSFORMER_STREAM,
    REDIS1_FEATURES_VP_STREAM,
)
from netwo_files.redis_tool import get_redis_connection


def _fmt_time(time_s: str) -> str:
    """Convert seconds-since-midnight string to HH:MM:SS."""
    try:
        s = int(time_s)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    except (ValueError, TypeError):
        return str(time_s)


def _print_consolidated(tf: dict, vp: dict | None) -> None:
    """Print merged features from both streams to stdout."""

    print(
        f"\n{'='*70}\n"
        f"SYMBOL: {tf.get('symbol')}  "
        f"date={tf.get('date')}  "
        f"time={_fmt_time(tf.get('time_s'))}  "
        f"bar={tf.get('bar_num')}"
    )

    print("--- Transformer Features ---")
    print(
        f"  pvol5={tf.get('parkinson_vol_5')}  "
        f"pvol15={tf.get('parkinson_vol_15')}  "
        f"pvol30={tf.get('parkinson_vol_30')}"
    )
    print(
        f"  ofi5={tf.get('ofi_5')}  "
        f"ofi15={tf.get('ofi_15')}  "
        f"ofi30={tf.get('ofi_30')}"
    )
    print(
        f"  vol_pct={tf.get('volume_percentile')}  "
        f"vol_mom={tf.get('volume_momentum')}"
    )
    print(
        f"  amihud={tf.get('amihud_illiquidity')}  "
        f"vwap_d={tf.get('vwap_distance')}"
    )
    print(
        f"  min_open={tf.get('minutes_since_open')}  "
        f"sess_flag={tf.get('is_first_last_30min')}"
    )

    print("--- Volume Profile ---")
    if vp is None:
        print("  NO features for volume")
    else:
        print(
            f"  POC={vp.get('poc_price')}  ({vp.get('poc_volume')})"
        )
        print(
            f"  VA=[{vp.get('value_area_low')} - {vp.get('value_area_high')}]  "
            f"TotalVol={vp.get('total_volume')}"
        )


def main() -> None:
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_FEATURES_TRANSFORMER_STREAM)

    print(
        f"[consolidator] Listening\n"
        f"-TF stream:  {REDIS1_FEATURES_TRANSFORMER_STREAM}\n"
        f"-VP stream:  {REDIS1_FEATURES_VP_STREAM}\n"
    )

    last_id_tf = "$"

    while True:
        # 1) Block until a new transformer feature arrives
        result = r.xread({REDIS1_FEATURES_TRANSFORMER_STREAM: last_id_tf}, count=1, block=5000)
        if not result:
            continue

        _, entries = result[0]
        entry_id, tf_fields = entries[0]
        last_id_tf = entry_id
        tf_symbol = tf_fields.get("symbol", "")

        # 2) Get latest VP entry (non-blocking)
        vp_entries = r.xrevrange(REDIS1_FEATURES_VP_STREAM, count=1)

        if not vp_entries:
            _print_consolidated(tf_fields, vp=None)
            continue

        _, vp_fields = vp_entries[0]
        vp_symbol = vp_fields.get("symbol", "")

        # 3) Symbol validation
        if tf_symbol != vp_symbol:
            print(
                f"[consolidator] SYMBOL MISMATCH: "
                f"tf={tf_symbol} vp={vp_symbol} — skipping"
            )
            continue

        # 4) Print merged features
        _print_consolidated(tf_fields, vp_fields)


if __name__ == "__main__":
    main()