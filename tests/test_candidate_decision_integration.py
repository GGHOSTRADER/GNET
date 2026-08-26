"""Integration coverage for the candidate-to-exact-decision service path.

The test uses real loopback TCP sockets at both TradeStation boundaries and an
in-memory Redis stream double between services. Docker-backed Redis protocol,
consumer-group recovery, and restart tests remain a separate test level.
"""

from __future__ import annotations

import socket
import threading
import time

from config.setting import (
    REDIS1_CANDIDATE_STREAM,
    REDIS1_DECISION_STREAM,
)
from inference import candidate_tcp_server
from inference.candidate_codec import candidate_from_redis_fields
from inference.signal_tcp_server import _serve
from inference.strategy_router import RouterCore, _publish


class _StopSignalServer(Exception):
    pass


class _MemoryRedis:
    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.acks: list[tuple[str, str, str]] = []
        self.added = threading.Event()
        self.signal_reads = 0

    def xadd(self, stream, fields, **_kwargs):
        entries = self.streams.setdefault(stream, [])
        entry_id = f"{len(entries) + 1}-0"
        entries.append((entry_id, dict(fields)))
        self.added.set()
        return entry_id

    def xack(self, stream, group, entry_id):
        self.acks.append((stream, group, entry_id))

    def xreadgroup(self, *_args, **_kwargs):
        self.signal_reads += 1
        if self.signal_reads == 1:
            return [[REDIS1_DECISION_STREAM, self.streams[REDIS1_DECISION_STREAM]]]
        if any(ack[0] == REDIS1_DECISION_STREAM for ack in self.acks):
            raise _StopSignalServer
        time.sleep(0.01)
        return []


def _run_signal_once(conn: socket.socket, redis_client: _MemoryRedis) -> None:
    try:
        _serve(conn, ("127.0.0.1", 0), redis_client)
    except _StopSignalServer:
        pass


def test_real_tcp_candidate_round_trip_through_router_and_signal_server(monkeypatch):
    redis_client = _MemoryRedis()
    monkeypatch.setattr(
        candidate_tcp_server,
        "get_redis_connection",
        lambda *_args, **_kwargs: redis_client,
    )

    with candidate_tcp_server._ThreadingServer(
        ("127.0.0.1", 0), candidate_tcp_server._CandidateHandler
    ) as candidate_server:
        candidate_thread = threading.Thread(
            target=candidate_server.handle_request,
            daemon=True,
        )
        candidate_thread.start()
        with socket.create_connection(candidate_server.server_address, timeout=2) as client:
            client.sendall(
                b"MA2CrossLE,MA-ES-30S-01,guid-integration,@ES,1260825,36000,101,1\n"
            )
        assert redis_client.added.wait(timeout=2)
        candidate_thread.join(timeout=2)

    candidate_id, candidate_fields = redis_client.streams[
        REDIS1_CANDIDATE_STREAM
    ][0]
    candidate = candidate_from_redis_fields(candidate_fields)
    core = RouterCore({"MA2CrossLE": lambda _fields: (True, 0.8125)})
    core.on_feature(
        {
            "symbol": "@ES",
            "date": "1260825",
            "time_s": "36000",
            "bar_num": "101",
        }
    )
    decisions = core.on_candidate(
        candidate,
        received_ns=int(candidate_fields["candidate_received_ns"]),
        entry_id=candidate_id,
    )
    _publish(redis_client, decisions)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    receiver = socket.create_connection(listener.getsockname(), timeout=2)
    sender, _ = listener.accept()
    listener.close()
    signal_thread = threading.Thread(
        target=_run_signal_once,
        args=(sender, redis_client),
        daemon=True,
    )
    signal_thread.start()
    payload = receiver.recv(4096).decode("utf-8").strip()
    receiver.sendall(b"ACK,MA-ES-30S-01,guid-integration\n")
    receiver.close()
    signal_thread.join(timeout=2)
    sender.close()

    assert payload == (
        "MA2CrossLE,MA-ES-30S-01,guid-integration,@ES,1260825,36000,101,1,"
        "ok,1,0.8125"
    )
    assert any(ack[0] == REDIS1_CANDIDATE_STREAM for ack in redis_client.acks)
    assert any(ack[0] == REDIS1_DECISION_STREAM for ack in redis_client.acks)
