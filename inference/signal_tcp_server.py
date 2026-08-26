"""
signal_tcp_server.py
====================

Reads exact-candidate decisions from the trade_decisions Redis stream and forwards them
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
import select
import time
from datetime import datetime

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
        try:
            n = conn.send(data[sent:])
        except OSError:
            # Windows reports normal DLL/client disconnects as errors such as
            # WSAECONNABORTED (10053) or WSAECONNRESET (10054). The decision
            # remains unacknowledged in Redis and is retried after reconnect.
            return False
        if n == 0:
            return False
        sent += n
    return True


def _recv_available(conn: socket.socket) -> bytes | None:
    """Return available ACK bytes, ``None`` for no data, or ``b''`` on close."""
    try:
        readable, _, exceptional = select.select([conn], [], [conn], 0)
        if exceptional:
            return b""
        if not readable:
            return None
        return conn.recv(4096)
    except (OSError, TypeError, ValueError):
        return b""


def _consume_ack_lines(
    buffer: bytes,
    inflight: dict[tuple[str, str], str],
    redis_client,
) -> bytes:
    """Acknowledge Redis only for exact DLL-consumption confirmations."""
    while b"\n" in buffer:
        raw_line, buffer = buffer.split(b"\n", 1)
        try:
            line = raw_line.decode("utf-8")
        except UnicodeDecodeError:
            print("[signal_server] ignored malformed non-UTF8 ACK")
            continue
        parts = line.split(",")
        if len(parts) != 3 or parts[0] != "ACK":
            print(f"[signal_server] ignored malformed ACK: {line!r}")
            continue
        key = parts[1], parts[2]
        entry_id = inflight.pop(key, None)
        if entry_id is None:
            print(
                f"[signal_server] ignored unknown ACK instance={key[0]} "
                f"candidate={key[1]}"
            )
            continue
        redis_client.xack(
            REDIS1_DECISION_STREAM,
            REDIS1_SIGNAL_DECISION_GROUP,
            entry_id,
        )
        print(
            f"~ {datetime.now().isoformat(timespec='milliseconds')} "
            f"[signal_server] TradeStation ACK instance={key[0]} "
            f"candidate={key[1]}"
        )
    return buffer


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
    """Keep decisions pending until the DLL confirms EasyLanguage consumption."""
    print(f"[signal_server] Client connected from {addr}")
    pending_id = "0-0"
    reading_pending = True
    ack_buffer = b""
    inflight: dict[tuple[str, str], str] = {}

    while True:
        ack_data = _recv_available(conn)
        if ack_data == b"":
            print(f"[signal_server] Client {addr} disconnected")
            return
        if ack_data:
            ack_buffer = _consume_ack_lines(
                ack_buffer + ack_data,
                inflight,
                redis_client,
            )

        result = redis_client.xreadgroup(
            REDIS1_SIGNAL_DECISION_GROUP,
            REDIS1_SIGNAL_CONSUMER,
            {REDIS1_DECISION_STREAM: pending_id if reading_pending else ">"},
            count=1,
            block=100,
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
        decision_key = fields.get("instance_id", ""), fields.get("candidate_id", "")
        if decision_key in inflight:
            continue
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
        inflight[decision_key] = entry_id
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
            f"~ {datetime.now().isoformat(timespec='milliseconds')} "
            f"[signal_server] sent; awaiting TradeStation ACK "
            f"strategy={fields.get('strategy_id', '')} "
            f"instance={fields.get('instance_id', '')} "
            f"candidate={fields.get('candidate_id', '')} "
            f"date={fields.get('date', '')} time_s={fields.get('time_s', '')} "
            f"candidate_to_delivery_ms={candidate_to_delivery_ms} "
            f"redis_to_delivery_ms={redis_to_delivery_ms} "
            f"socket_send_ms={socket_send_ms:.3f}"
        )


def run() -> None:
    print(
        "[signal_server] Ready\n"
        f"  TCP Host: {TCP_SIGNAL_HOST}\n"
        f"  TCP Port: {TCP_SIGNAL_PORT}\n"
        f"  Redis Host: {REDIS1_HOST}\n"
        f"  Redis Port: {REDIS1_PORT}\n"
        f"  Redis Stream: {REDIS1_DECISION_STREAM}\n"
    )
    redis_client = get_redis_connection(
        REDIS1_HOST, REDIS1_PORT, REDIS1_DECISION_STREAM
    )
    print(
        "[signal_server] Purpose: delivers decision to TradeStation."
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
