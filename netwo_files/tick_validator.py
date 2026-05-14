"""
tick_validator.py
=================

Reads raw ticks from Redis tick_data_raw, validates them,
and pushes clean ticks to Redis tick_data_validated.

Flow
----
tick_data_raw -> parse + cast + validate -> tick_data_validated

Design
------
Validation is intentionally separated from ingestion (tcp_to_redis_ticks.py)
so the TCP server can drain the kernel buffer at maximum speed.
This script runs as a separate process and handles all type checking
and contract enforcement without blocking the ingest path.

Function Summary
----------------
1) main()  -- connects to Redis, reads tick_data_raw in a blocking loop,
              calls parse_raw_tick_line (cast) + validate_tick_sequence (sequence check),
              pushes valid ticks to tick_data_validated, drops and logs failures

Run
---
python -m netwo_files.tick_validator
"""

from datetime import datetime
from typing import Optional

from config.setting import (
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_TICK_RAW_STREAM,
    REDIS1_TICK_VALIDATED_STREAM,
)
from netwo_files.redis_tool import get_redis_connection
from netwo_files.tick_codec import (
    parse_raw_tick_line,
    tick_to_redis_fields,
    parse_xread_raw_ticks,
    TickDecodeError,
)
from netwo_files.tick_contract import (
    Tick,
    validate_tick_sequence,
    TickContractError,
)


def main() -> None:
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_TICK_RAW_STREAM)

    print(
        f"[tick_validator] Connected\n"
        f"-Reading:  {REDIS1_TICK_RAW_STREAM}\n"
        f"-Writing:  {REDIS1_TICK_VALIDATED_STREAM}\n"
    )

    last_id: str = "$"
    prev_tick: Optional[Tick] = None

    while True:
        xread_result = r.xread(
            {REDIS1_TICK_RAW_STREAM: last_id},
            count=500,
            block=100,
        )

        if not xread_result:
            continue

        entries = parse_xread_raw_ticks(xread_result)

        for entry_id, raw_line in entries:
            last_id = entry_id

            if not raw_line:
                print(f"[tick_validator] Empty raw_tick field — skipping entry {entry_id}")
                continue

            # 1) Cast types
            try:
                tick = parse_raw_tick_line(raw_line)
            except (TickDecodeError, TickContractError) as e:
                print(f"[tick_validator] INVALID: {e} | raw={raw_line}")
                continue

            # 2) Sequence check
            try:
                validate_tick_sequence(prev_tick, tick)
            except TickContractError as e:
                print(f"[tick_validator] SEQUENCE ERROR: {e} | raw={raw_line}")
                continue

            prev_tick = tick

            # 3) Push validated tick to clean stream
            r.xadd(
                REDIS1_TICK_VALIDATED_STREAM,
                tick_to_redis_fields(tick),
                maxlen=50_000,
                approximate=True,
            )

            print(f"{datetime.now().isoformat()}  OK  {raw_line}")


if __name__ == "__main__":
    main()
