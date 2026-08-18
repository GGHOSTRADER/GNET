"""
signal_tcp_server.py
====================

Reads correlated decisions from the trade_decisions Redis stream and forwards them
to TradeStation over a persistent TCP connection.

Flow
----
  trade_decisions (Redis) -> TCP 9011 -> SignalBridge.dll -> EasyLanguage

Protocol (one line per signal)
-------------------------------
  strategy_id,instance_id,candidate_id,symbol,date,time_s,bar_num,direction,status,approved,prob\n

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
import time

from config.setting import (
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_DECISION_STREAM,
    TCP_SIGNAL_HOST,
    TCP_SIGNAL_PORT,
    REDIS1_SIGNAL_DECISION_GROUP,
    REDIS1_SIGNAL_CONSUMER,
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


DECISION_FIELDS = (
    "strategy_id", "instance_id", "candidate_id", "symbol", "date", "time_s",
    "bar_num", "direction", "status", "approved", "prob",
)


def _decision_line(fields: dict[str, str]) -> bytes:
    values = []
    for name in DECISION_FIELDS:
        value = fields.get(name, "")
        if "," in value or "\n" in value or "\r" in value:
            raise ValueError(f"unsafe {name} in decision")
        values.append(value)
    return (",".join(values) + "\n").encode("utf-8")


def _serve(conn: socket.socket, addr: tuple, redis_client) -> None:
    """Stream decisions, acknowledging each only after successful delivery."""
    print(f"[signal_server] Client connected from {addr}")
    pending_id = "0-0"
    reading_pending = True

    while True:
        result = redis_client.xreadgroup(
            REDIS1_SIGNAL_DECISION_GROUP,
            REDIS1_SIGNAL_CONSUMER,
            {REDIS1_DECISION_STREAM: pending_id if reading_pending else ">"},
            count=1,
            block=5000,
        )
        if not result:
            if reading_pending:
                reading_pending = False
            continue

        # Redis can represent "stream exists, but this consumer has no pending
        # entries" as [[stream_name, []]]. Treat that exactly like an empty
        # read and switch from pending recovery to new-message consumption.
        entry = next(
            (entries[0] for _, entries in result if entries),
            None,
        )
        if entry is None:
            if reading_pending:
                reading_pending = False
            continue

        entry_id, fields = entry
        if reading_pending:
            pending_id = entry_id
        try:
            line = _decision_line(fields)
        except ValueError as exc:
            print(f"[signal_server] rejected decision: {exc}")
            redis_client.xack(
                REDIS1_DECISION_STREAM,
                REDIS1_SIGNAL_DECISION_GROUP,
                entry_id,
            )
            continue

        delivery_started_ns = time.time_ns()
        send_started_ns = time.perf_counter_ns()
        if not _send_all(conn, line):
            print(f"[signal_server] Client {addr} disconnected (send failed)")
            return
        socket_send_ms = (time.perf_counter_ns() - send_started_ns) / 1_000_000

        redis_client.xack(
            REDIS1_DECISION_STREAM,
            REDIS1_SIGNAL_DECISION_GROUP,
            entry_id,
        )
        candidate_received_ns = fields.get("candidate_received_ns")
        published_ns = fields.get("decision_published_ns")
        candidate_to_delivery_ms = (
            "n/a"
            if not candidate_received_ns
            else f"{max(0, delivery_started_ns - int(candidate_received_ns)) / 1_000_000:.3f}"
        )
        redis_to_delivery_ms = (
            "n/a"
            if not published_ns
            else f"{max(0, delivery_started_ns - int(published_ns)) / 1_000_000:.3f}"
        )
        print(
            f"[signal_server] delivered strategy={fields.get('strategy_id', '')} "
            f"instance={fields.get('instance_id', '')} "
            f"candidate={fields.get('candidate_id', '')} "
            f"candidate_to_delivery_ms={candidate_to_delivery_ms} "
            f"redis_to_delivery_ms={redis_to_delivery_ms} "
            f"socket_send_ms={socket_send_ms:.3f}"
        )


def run() -> None:
    print(
        f"[signal_server] Listening on {TCP_SIGNAL_HOST}:{TCP_SIGNAL_PORT}\n"
        f"  reading: {REDIS1_DECISION_STREAM}\n"
    )

    redis_client = get_redis_connection(
        REDIS1_HOST, REDIS1_PORT, REDIS1_DECISION_STREAM
    )
    try:
        redis_client.xgroup_create(
            REDIS1_DECISION_STREAM,
            REDIS1_SIGNAL_DECISION_GROUP,
            id="$",
            mkstream=True,
        )
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((TCP_SIGNAL_HOST, TCP_SIGNAL_PORT))
        srv.listen(1)

        while True:
            conn, addr = srv.accept()
            with conn:
                _serve(conn, addr, redis_client)
            print("[signal_server] Waiting for next connection...")


if __name__ == "__main__":
    run()
