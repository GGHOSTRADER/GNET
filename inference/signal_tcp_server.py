"""
signal_tcp_server.py
====================

Reads trade signals from the trade_signal Redis stream and forwards them
to TradeStation over a persistent TCP connection.

Flow
----
  trade_signal (Redis) -> TCP 9011 -> SignalBridge.dll -> EasyLanguage

Protocol (one line per signal)
-------------------------------
  symbol,signal,prob\n
  e.g.  "ESM25,1,0.7231\n"

Design
------
- This process is the TCP SERVER (listens on 9011).
- TradeStation's SignalBridge.dll is the client (connects once, stays connected).
- When a signal fires, the line is written immediately to the open socket.
- If the client disconnects, the server waits for a new connection.

Run
---
  python -m inference.signal_tcp_server
"""

from __future__ import annotations

import socket

from config.setting import (
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_SIGNAL_STREAM,
    TCP_SIGNAL_HOST,
    TCP_SIGNAL_PORT,
)
from netwo_files.redis_tool import get_redis_connection


def _send_all(conn: socket.socket, data: bytes) -> bool:
    sent = 0
    while sent < len(data):
        n = conn.send(data[sent:])
        if n == 0:
            return False
        sent += n
    return True


def _serve(conn: socket.socket, addr: tuple) -> None:
    """Stream signals to one connected client until it disconnects."""
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_SIGNAL_STREAM)
    last_id = "$"

    print(f"[signal_server] Client connected from {addr}")

    while True:
        result = r.xread({REDIS1_SIGNAL_STREAM: last_id}, count=1, block=5000)
        if not result:
            continue

        _, entries = result[0]
        entry_id, fields = entries[0]
        last_id = entry_id

        symbol = fields.get("symbol", "")
        signal = fields.get("signal", "0")
        prob   = fields.get("prob", "0.0")

        line = f"{symbol},{signal},{prob}\n".encode("utf-8")

        if not _send_all(conn, line):
            print(f"[signal_server] Client {addr} disconnected (send failed)")
            return

        print(f"[signal_server] Sent → {line.decode().strip()}")


def run() -> None:
    print(
        f"[signal_server] Listening on {TCP_SIGNAL_HOST}:{TCP_SIGNAL_PORT}\n"
        f"  reading: {REDIS1_SIGNAL_STREAM}\n"
    )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((TCP_SIGNAL_HOST, TCP_SIGNAL_PORT))
        srv.listen(1)

        while True:
            conn, addr = srv.accept()
            with conn:
                _serve(conn, addr)
            print("[signal_server] Waiting for next connection...")


if __name__ == "__main__":
    run()
