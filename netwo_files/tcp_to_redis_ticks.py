"""
tcp_to_redis_ticks.py
=====================

Ultra-lean TCP server for high-frequency tick data.

Design principle
----------------
DO NOT validate, parse, or cast here.
Drain the kernel buffer as fast as possible and push raw lines to Redis.
All validation happens downstream in tick_validator.py.

GIL note
--------
The Python GIL is held during r.xadd() — redis-py is pure Python and does
not release the GIL on socket writes. This means the recv loop is blocked
for the duration of each xadd call (~50µs on TCP loopback). At 400 ticks/s
this adds up to ~20ms/s of GIL contention. Acceptable at current volumes,
but a hard ceiling if tick rate grows significantly. The SO_RCVBUF=1MB
buffer absorbs bursts that arrive while the GIL is held by xadd.

Flow
----
TradeStation -> TickBridge.dll -> TCP port 9010 -> this server -> Redis tick_data_raw

Function Summary
----------------
1) main()  -- binds TCP port 9010 and keeps accepting replacement clients.
2) _handle_client() -- drains one client, splits on newline, and pushes each raw
                       CSV line as {"raw_tick": line}. Zero parsing or validation.
3) _accept_forever() -- survives graceful disconnects and connection resets.

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


def _handle_client(conn, redis_client) -> None:
    """Drain one tick-DLL connection until it closes."""
    buf = b""
    with conn:
        while True:
            data = conn.recv(4096)
            if not data:
                return
            buf += data

            while b"\n" in buf:
                raw_line, buf = buf.split(b"\n", 1)
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                redis_client.xadd(
                    REDIS1_TICK_RAW_STREAM,
                    {"raw_tick": line},
                    maxlen=50_000,
                    approximate=True,
                )
                print(f"{datetime.now().isoformat()}  {line}")


def _accept_forever(server, redis_client) -> None:
    """Accept replacement DLL clients without terminating this process."""
    while True:
        conn, addr = server.accept()
        print(f"[tick_server] Connection from {addr}")
        try:
            _handle_client(conn, redis_client)
            print("[tick_server] Client disconnected")
        except OSError as exc:
            print(f"[tick_server] Client connection lost: {exc}")
        print("[tick_server] Waiting for TradeStation to reconnect...")


def main() -> None:
    redis_client = get_redis_connection(
        REDIS1_HOST, REDIS1_PORT, REDIS1_TICK_RAW_STREAM
    )
    print(f"[tick_server] Listening TCP\n-Host:{TCP_TICK_HOST}\n-Port:{TCP_TICK_PORT}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
        server.bind((TCP_TICK_HOST, TCP_TICK_PORT))
        server.listen(5)
        _accept_forever(server, redis_client)


if __name__ == "__main__":
    main()
