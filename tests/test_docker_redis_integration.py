"""Docker-backed integration tests for durable candidate/decision delivery.

These tests create one isolated, disposable Redis container. They never use or
modify the live ``redis1`` container or GNET's production stream names.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
import uuid

import pytest
import redis

from inference import signal_tcp_server, strategy_router
from inference.candidate_codec import candidate_from_redis_fields
from inference.candidate_codec import candidate_to_redis_fields, parse_candidate_line
from inference.signal_tcp_server import _serve
from inference.strategy_router import RouterCore, _publish


class _StopServe(Exception):
    pass


class _RedisReadLimiter:
    def __init__(self, client, allowed_reads: int):
        self._client = client
        self._allowed_reads = allowed_reads
        self._reads = 0

    def __getattr__(self, name):
        return getattr(self._client, name)

    def xreadgroup(self, *args, **kwargs):
        self._reads += 1
        if self._reads > self._allowed_reads:
            raise _StopServe
        return self._client.xreadgroup(*args, **kwargs)


class _AbortedConnection:
    def send(self, _data):
        raise ConnectionAbortedError(10053, "simulated DLL disconnect")


class _CollectingConnection:
    def __init__(self):
        self.payload = bytearray()

    def send(self, data):
        self.payload.extend(data)
        return len(data)


@pytest.fixture(scope="module")
def docker_redis():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is not installed")

    daemon = subprocess.run(
        [docker, "info"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if daemon.returncode != 0:
        pytest.skip("Docker engine is unavailable")

    container_name = f"gnet-redis-test-{uuid.uuid4().hex[:12]}"
    started = subprocess.run(
        [
            docker,
            "run",
            "--detach",
            "--rm",
            "--name",
            container_name,
            "--publish",
            "127.0.0.1::6379",
            "redis",
            "redis-server",
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if started.returncode != 0:
        raise RuntimeError(f"could not start isolated Redis: {started.stderr.strip()}")

    try:
        published = subprocess.run(
            [docker, "port", container_name, "6379/tcp"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
        host, port_text = published.rsplit(":", 1)
        client = redis.Redis(host=host, port=int(port_text), decode_responses=True)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if client.ping():
                    break
            except redis.RedisError:
                time.sleep(0.05)
        else:
            raise RuntimeError("isolated Redis did not become ready")
        yield client
    finally:
        subprocess.run(
            [docker, "rm", "--force", container_name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )


def _names(prefix: str) -> tuple[str, str, str, str]:
    suffix = uuid.uuid4().hex
    return (
        f"{prefix}:candidates:{suffix}",
        f"{prefix}:decisions:{suffix}",
        f"{prefix}:group:{suffix}",
        f"{prefix}:consumer:{suffix}",
    )


def _decision(candidate_id: str) -> dict[str, str]:
    now_ns = str(time.time_ns())
    return {
        "strategy_id": "MA2CrossLE",
        "instance_id": "MA-ES-30S-01",
        "candidate_id": candidate_id,
        "symbol": "@ES",
        "date": "1260826",
        "time_s": "36000",
        "bar_num": "101",
        "direction": "1",
        "status": "ok",
        "approved": "1",
        "prob": "0.75",
        "candidate_received_ns": now_ns,
        "decision_published_ns": now_ns,
    }


def test_router_publishes_decision_then_acknowledges_candidate(
    docker_redis, monkeypatch
):
    candidates, decisions, group, consumer = _names("router")
    monkeypatch.setattr(strategy_router, "REDIS1_CANDIDATE_STREAM", candidates)
    monkeypatch.setattr(strategy_router, "REDIS1_DECISION_STREAM", decisions)
    monkeypatch.setattr(strategy_router, "REDIS1_ROUTER_CANDIDATE_GROUP", group)

    docker_redis.xgroup_create(candidates, group, id="0-0", mkstream=True)
    candidate = parse_candidate_line(
        "MA2CrossLE,MA-ES-30S-01,guid-docker,@ES,1260826,36000,101,1"
    )
    candidate_fields = candidate_to_redis_fields(candidate)
    candidate_fields["candidate_received_ns"] = str(time.time_ns())
    entry_id = docker_redis.xadd(candidates, candidate_fields)
    result = docker_redis.xreadgroup(group, consumer, {candidates: ">"}, count=1)
    delivered_id, delivered_fields = result[0][1][0]
    assert delivered_id == entry_id

    core = RouterCore({"MA2CrossLE": lambda _fields: (True, 0.75)})
    core.on_feature(
        {"symbol": "@ES", "date": "1260826", "time_s": "36000", "bar_num": "1"}
    )
    routed = core.on_candidate(
        candidate_from_redis_fields(delivered_fields),
        received_ns=int(delivered_fields["candidate_received_ns"]),
        entry_id=delivered_id,
    )
    _publish(docker_redis, routed)

    assert docker_redis.xpending(candidates, group)["pending"] == 0
    stored = docker_redis.xrevrange(decisions, count=1)[0][1]
    assert stored["candidate_id"] == "guid-docker"
    assert stored["status"] == "ok"
    assert stored["approved"] == "1"


def test_unacknowledged_decision_is_recovered_after_dll_reconnect(
    docker_redis, monkeypatch
):
    _candidates, decisions, group, consumer = _names("signal-recovery")
    monkeypatch.setattr(signal_tcp_server, "REDIS1_DECISION_STREAM", decisions)
    monkeypatch.setattr(signal_tcp_server, "REDIS1_SIGNAL_DECISION_GROUP", group)
    monkeypatch.setattr(signal_tcp_server, "REDIS1_SIGNAL_CONSUMER", consumer)

    docker_redis.xgroup_create(decisions, group, id="0-0", mkstream=True)
    docker_redis.xadd(decisions, _decision("guid-recover"))

    real_recv_available = signal_tcp_server._recv_available
    monkeypatch.setattr(signal_tcp_server, "_recv_available", lambda _conn: None)
    _serve(_AbortedConnection(), ("127.0.0.1", 1), docker_redis)
    assert docker_redis.xpending(decisions, group)["pending"] == 1

    server_socket, dll_socket = socket.socketpair()
    monkeypatch.setattr(
        signal_tcp_server,
        "_recv_available",
        real_recv_available,
    )

    error = []

    def serve_recovery():
        try:
            _serve(server_socket, ("127.0.0.1", 2), docker_redis)
        except Exception as exc:
            error.append(exc)

    import threading

    thread = threading.Thread(target=serve_recovery, daemon=True)
    thread.start()
    payload = dll_socket.recv(4096)
    dll_socket.sendall(b"ACK,MA-ES-30S-01,guid-recover\n")
    deadline = time.monotonic() + 2
    while docker_redis.xpending(decisions, group)["pending"] != 0:
        if time.monotonic() >= deadline:
            raise AssertionError("TradeStation ACK did not clear Redis pending entry")
        time.sleep(0.01)
    dll_socket.close()
    thread.join(timeout=2)
    server_socket.close()

    assert not error
    assert b"guid-recover" in payload
    assert docker_redis.xpending(decisions, group)["pending"] == 0


def test_malformed_decision_is_acknowledged_without_socket_delivery(
    docker_redis, monkeypatch
):
    _candidates, decisions, group, consumer = _names("signal-malformed")
    monkeypatch.setattr(signal_tcp_server, "REDIS1_DECISION_STREAM", decisions)
    monkeypatch.setattr(signal_tcp_server, "REDIS1_SIGNAL_DECISION_GROUP", group)
    monkeypatch.setattr(signal_tcp_server, "REDIS1_SIGNAL_CONSUMER", consumer)

    docker_redis.xgroup_create(decisions, group, id="0-0", mkstream=True)
    malformed = _decision("guid-malformed")
    malformed["strategy_id"] = "unsafe\nstrategy"
    docker_redis.xadd(decisions, malformed)

    connection = _CollectingConnection()
    limited = _RedisReadLimiter(docker_redis, allowed_reads=2)
    monkeypatch.setattr(signal_tcp_server, "_recv_available", lambda _conn: None)
    with pytest.raises(_StopServe):
        _serve(connection, ("127.0.0.1", 3), limited)

    assert connection.payload == b""
    assert docker_redis.xpending(decisions, group)["pending"] == 0


def test_consumer_offset_survives_client_restart(docker_redis):
    candidates, _decisions, group, consumer = _names("offset")
    docker_redis.xgroup_create(candidates, group, id="0-0", mkstream=True)
    entry_id = docker_redis.xadd(candidates, {"candidate_id": "durable-guid"})
    connection = docker_redis.connection_pool.connection_kwargs

    first_client = redis.Redis(
        host=connection["host"],
        port=connection["port"],
        decode_responses=True,
    )
    first = first_client.xreadgroup(group, consumer, {candidates: ">"}, count=1)
    assert first[0][1][0][0] == entry_id
    first_client.close()

    replacement = redis.Redis(
        host=connection["host"],
        port=connection["port"],
        decode_responses=True,
    )
    pending = replacement.xreadgroup(group, consumer, {candidates: "0-0"}, count=1)
    assert pending[0][1][0][0] == entry_id
    replacement.xack(candidates, group, entry_id)
    assert replacement.xpending(candidates, group)["pending"] == 0
    replacement.close()
