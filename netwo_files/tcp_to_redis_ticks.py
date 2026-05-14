"""
tcp_to_redis_ticks.py
=====================

Ultra-lean TCP server for high-frequency tick data.

Design principle
----------------
DO NOT validate, parse, or cast here.
Drain the kernel buffer as fast as possible and push raw lines to Redis.
All validation happens downstream in tick_validator.py.

Flow
----
TradeStation -> TickBridge.dll -> TCP port 9010 -> this server -> Redis tick_data_raw

Function Summary
----------------
1) main()  -- binds TCP port 9010, accepts one client, reads kernel buffer in a loop,
              splits on newline, pushes each raw CSV line as {"raw_tick": line}
              to tick_data_raw via xadd. Zero parsing, zero validation.

Run
---
python -m netwo_files.tcp_to_redis_ticks
"""

import socket
from datetime import datetime

from config.setting import (
    TCP_TICK_HOST,
    TCP_TICK_PORT,
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_TICK_RAW_STREAM,
)
from netwo_files.redis_tool import get_redis_connection


def main() -> None:
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_TICK_RAW_STREAM)

    print(f"[tick_server] Listening TCP\n-Host:{TCP_TICK_HOST}\n-Port:{TCP_TICK_PORT}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)  # 1MB kernel recv buffer
        s.bind((TCP_TICK_HOST, TCP_TICK_PORT))
        s.listen(5)

        conn, addr = s.accept()
        print(f"[tick_server] Connection from {addr}")

        buf = b""
        with conn:
            while True:
                data = conn.recv(4096)
                if not data:
                    print("[tick_server] Client disconnected")
                    break

                buf += data

                while b"\n" in buf:
                    raw_line, buf = buf.split(b"\n", 1)
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue

                    # Push raw line straight to Redis — no parsing, no validation
                    r.xadd(
                        REDIS1_TICK_RAW_STREAM,
                        {"raw_tick": line},
                        maxlen=50_000,
                        approximate=True,
                    )

                    print(f"{datetime.now().isoformat()}  {line}")


if __name__ == "__main__":
    main()
