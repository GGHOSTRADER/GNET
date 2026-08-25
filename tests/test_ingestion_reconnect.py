import pytest

from netwo_files import tcp_to_redis_connection as bar_server
from netwo_files import tcp_to_redis_ticks as tick_server


class StopAcceptLoop(Exception):
    pass


class FakeConnection:
    def __init__(self, responses):
        self.responses = list(responses)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True

    def recv(self, _capacity):
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeServer:
    def __init__(self, connections):
        self.connections = list(connections)
        self.accept_count = 0

    def accept(self):
        if not self.connections:
            raise StopAcceptLoop
        self.accept_count += 1
        return self.connections.pop(0), ("127.0.0.1", 50000 + self.accept_count)


class FakeRedis:
    def __init__(self):
        self.added = []

    def xadd(self, stream, fields, **kwargs):
        self.added.append((stream, fields, kwargs))


def test_bar_server_accepts_replacement_client_and_discards_partial_buffer():
    valid_bar = (
        b"@ES,1260819,36000,100.0,101.0,99.5,100.5,4,1,100.2,10\n"
    )
    first = FakeConnection([b"incomplete-bar", b""])
    second = FakeConnection([valid_bar, b""])
    server = FakeServer([first, second])
    redis_client = FakeRedis()

    with pytest.raises(StopAcceptLoop):
        bar_server._accept_forever(server, redis_client)

    assert server.accept_count == 2
    assert first.closed and second.closed
    assert len(redis_client.added) == 1
    assert redis_client.added[0][1]["bar_num"] == "10"


def test_tick_server_accepts_replacement_client_after_connection_reset():
    valid_tick = b"@ES,1260819,36000,100.25,100.25,1,0,20\n"
    first = FakeConnection([ConnectionResetError("simulated reset")])
    second = FakeConnection([valid_tick, b""])
    server = FakeServer([first, second])
    redis_client = FakeRedis()

    with pytest.raises(StopAcceptLoop):
        tick_server._accept_forever(server, redis_client)

    assert server.accept_count == 2
    assert first.closed and second.closed
    assert len(redis_client.added) == 1
    published = redis_client.added[0][1]
    assert published["raw_tick"] == "@ES,1260819,36000,100.25,100.25,1,0,20"
    assert int(published["tcp_received_ns"]) > 0
