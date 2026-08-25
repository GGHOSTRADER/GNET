import pytest

from inference.candidate_codec import (
    candidate_from_redis_fields,
    candidate_to_redis_fields,
    parse_candidate_line,
)
from inference.candidate_contract import CandidateError
from inference.signal_tcp_server import _decision_line, _serve
from inference.strategy_router import RouterCore, _publish, _xread_has_entries


def _candidate(candidate_id="MA-101"):
    return parse_candidate_line(
        f"MA2CrossLE,MA-ES-01,{candidate_id},ESM26,1260816,36000,101,1"
    )


def _features():
    return {
        "symbol": "ESM26",
        "date": "1260816",
        "time_s": "36000",
        "bar_num": "101",
    }


def test_xread_empty_stream_wrapper_contains_no_entries():
    assert not _xread_has_entries([["trade_candidates", []]])
    assert not _xread_has_entries([])
    assert _xread_has_entries([["trade_candidates", [["1-0", {}]]]])


def test_candidate_codec_round_trip():
    candidate = _candidate()
    assert candidate_from_redis_fields(candidate_to_redis_fields(candidate)) == candidate


def test_candidate_rejects_invalid_direction():
    try:
        parse_candidate_line("MA2CrossLE,MA-ES-01,id,ES,1260816,36000,101,0")
    except CandidateError:
        pass
    else:
        raise AssertionError("invalid direction was accepted")


def test_router_matches_when_feature_arrives_first():
    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.75)})
    assert core.on_feature(_features()) == []
    decision = core.on_candidate(_candidate())[0]
    assert decision["status"] == "ok"
    assert decision["instance_id"] == "MA-ES-01"
    assert decision["approved"] == "1"
    assert decision["prob"] == "0.75"


def test_router_matches_when_candidate_arrives_first():
    core = RouterCore({"MA2CrossLE": lambda fields: (False, 0.4)})
    assert core.on_candidate(_candidate(), now=10.0) == []
    decision = core.on_feature(_features())[0]
    assert decision["status"] == "ok"
    assert decision["approved"] == "0"


def test_router_ignores_cross_study_bar_number_difference():
    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.9)}, timeout_s=0.25)
    core.on_candidate(_candidate(), now=10.0)
    same_market_bar = _features()
    same_market_bar["bar_num"] = "102"
    decision = core.on_feature(same_market_bar)[0]
    assert decision["status"] == "ok"
    assert decision["approved"] == "1"


def test_router_rejects_nonmatching_timestamp_then_times_out():
    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.9)}, timeout_s=0.25)
    core.on_candidate(_candidate(), now=10.0)
    wrong = _features()
    wrong["time_s"] = "36030"
    assert core.on_feature(wrong) == []
    decision = core.expire(now=10.26)[0]
    assert decision["status"] == "missing_features"
    assert decision["approved"] == "0"


def test_router_deduplicates_candidate_id():
    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.8)})
    core.on_feature(_features())
    assert len(core.on_candidate(_candidate())) == 1
    assert core.on_candidate(_candidate()) == []


def test_decision_wire_protocol_keeps_correlation_fields():
    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.8)})
    core.on_feature(_features())
    decision = core.on_candidate(_candidate())[0]
    assert _decision_line(decision).decode().strip() == (
        "MA2CrossLE,MA-ES-01,MA-101,ESM26,1260816,36000,101,1,ok,1,0.8"
    )


def test_same_strategy_instances_receive_exact_candidate_decisions():
    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.8)})
    core.on_feature(_features())
    first = core.on_candidate(_candidate("first"))[0]
    second_candidate = parse_candidate_line(
        "MA2CrossLE,MA-ES-02,second,ESM26,1260816,36000,101,1"
    )
    second = core.on_candidate(second_candidate)[0]
    assert first["instance_id"] == "MA-ES-01"
    assert second["instance_id"] == "MA-ES-02"


def test_decision_contains_exact_candidate_latency_fields():
    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.8)})
    core.on_feature(_features())
    decision = core.on_candidate(_candidate(), received_ns=1)[0]
    assert decision["candidate_received_ns"] == "1"
    assert float(decision["feature_wait_ms"]) >= 0
    assert float(decision["inference_ms"]) >= 0
    assert float(decision["router_total_ms"]) >= 0


def test_decision_keeps_candidate_stream_entry_for_acknowledgement():
    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.8)})
    core.on_feature(_features())
    decision = core.on_candidate(_candidate(), entry_id="123-0")[0]
    assert decision["_candidate_entry_id"] == "123-0"


def test_publish_writes_decision_before_acknowledging_candidate():
    class FakeRedis:
        def __init__(self):
            self.calls = []

        def xadd(self, stream, fields, **kwargs):
            self.calls.append(("xadd", stream, fields.copy()))

        def xack(self, stream, group, entry_id):
            self.calls.append(("xack", stream, group, entry_id))

    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.8)})
    core.on_feature(_features())
    decision = core.on_candidate(_candidate(), entry_id="123-0")[0]
    redis_client = FakeRedis()

    _publish(redis_client, [decision])

    assert redis_client.calls[0][0] == "xadd"
    assert "_candidate_entry_id" not in redis_client.calls[0][2]
    assert redis_client.calls[1][-1] == "123-0"


def test_signal_server_acknowledges_only_after_socket_delivery():
    class StopLoop(Exception):
        pass

    class FakeConnection:
        def __init__(self, events):
            self.events = events

        def send(self, data):
            self.events.append("send")
            return len(data)

    class FakeRedis:
        def __init__(self, fields, events):
            self.fields = fields
            self.events = events
            self.reads = 0

        def xreadgroup(self, *args, **kwargs):
            self.reads += 1
            if self.reads == 1:
                return [["trade_decisions", [["200-0", self.fields]]]]
            raise StopLoop

        def xack(self, stream, group, entry_id):
            self.events.append("ack")

    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.8)})
    core.on_feature(_features())
    fields = core.on_candidate(_candidate())[0]
    events = []

    with pytest.raises(StopLoop):
        _serve(FakeConnection(events), ("local", 1), FakeRedis(fields, events))

    assert events == ["send", "ack"]


def test_signal_server_handles_empty_pending_batch_before_new_decision():
    class StopLoop(Exception):
        pass

    class FakeConnection:
        def __init__(self, events):
            self.events = events

        def send(self, data):
            self.events.append("send")
            return len(data)

    class FakeRedis:
        def __init__(self, fields, events):
            self.fields = fields
            self.events = events
            self.requested_ids = []

        def xreadgroup(self, *args, **kwargs):
            requested_id = next(iter(args[2].values()))
            self.requested_ids.append(requested_id)
            if len(self.requested_ids) == 1:
                return [["trade_decisions", []]]
            if len(self.requested_ids) == 2:
                return [["trade_decisions", [["201-0", self.fields]]]]
            raise StopLoop

        def xack(self, stream, group, entry_id):
            self.events.append("ack")

    core = RouterCore({"MA2CrossLE": lambda fields: (True, 0.8)})
    core.on_feature(_features())
    fields = core.on_candidate(_candidate())[0]
    events = []
    redis_client = FakeRedis(fields, events)

    with pytest.raises(StopLoop):
        _serve(FakeConnection(events), ("local", 1), redis_client)

    assert redis_client.requested_ids[:2] == ["0-0", ">"]
    assert events == ["send", "ack"]


def test_symbol_contract_accepts_tradestation_continuous_symbol():
    candidate = parse_candidate_line(
        "MA2CrossLE,MA-ES-01,guid-1,@ES,1260816,36000,101,1"
    )
    assert candidate.symbol == "@ES"
