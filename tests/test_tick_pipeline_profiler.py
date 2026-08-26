from netwo_files.tick_pipeline_profiler import collect_pipeline_times, format_report


class FakeRedis:
    def __init__(self, streams):
        self.streams = streams

    def xrevrange(self, stream, count):
        return self.streams.get(stream, [])[:count]


def test_collect_pipeline_times_joins_exact_tick_across_all_streams():
    redis_client = FakeRedis(
        {
            "tick_data_raw": [
                (
                    b"1001-0",
                    {
                        b"raw_tick": b"@ES,1260825,35999,6500.0,6500.0,1,0,42",
                        b"tcp_received_ns": b"1000000000",
                    },
                )
            ],
            "tick_data_validated": [
                (
                    b"1004-0",
                    {
                        b"symbol": b"@ES",
                        b"date": b"1260825",
                        b"time": b"35999",
                        b"bar_num": b"42",
                        b"raw_entry_id": b"1001-0",
                        b"validator_received_ns": b"1002000000",
                    },
                )
            ],
            "features_volume_profile": [
                (
                    b"1009-0",
                    {
                        b"source_raw_entry_id": b"1001-0",
                        b"source_tcp_received_ns": b"1000000000",
                        b"source_validator_received_ns": b"1002000000",
                        b"source_validated_published_ms": b"1004",
                        b"snapshot_started_ns": b"1007000000",
                        b"snapshot_finished_ns": b"1007500000",
                    },
                )
            ],
        }
    )

    samples = collect_pipeline_times(redis_client, count=100)

    assert len(samples) == 2
    assert samples[0].tcp_received_ms == 1000.0
    assert samples[0].raw_published_ms == 1001.0
    assert samples[0].validator_received_ms == 1002.0
    assert samples[0].validated_published_ms == 1004.0
    assert samples[1].feature_published_ms == 1009.0
    assert samples[1].snapshot_started_ms == 1007.0
    assert samples[1].snapshot_finished_ms == 1007.5


def test_format_report_shows_each_pipeline_hop():
    redis_client = FakeRedis(
        {
            "tick_data_raw": [
                (
                    "1001-0",
                    {
                        "raw_tick": "@ES,1260825,35999,6500.0,6500.0,1,0,42",
                        "tcp_received_ns": "1000000000",
                    },
                )
            ],
            "tick_data_validated": [
                (
                    "1004-0",
                    {
                        "symbol": "@ES",
                        "date": "1260825",
                        "time": "35999",
                        "bar_num": "42",
                        "raw_entry_id": "1001-0",
                        "validator_received_ns": "1002000000",
                    },
                )
            ],
            "features_volume_profile": [
                (
                    "1009-0",
                    {
                        "source_raw_entry_id": "1001-0",
                        "source_tcp_received_ns": "1000000000",
                        "source_validator_received_ns": "1002000000",
                        "source_validated_published_ms": "1004",
                        "snapshot_started_ns": "1007000000",
                        "snapshot_finished_ns": "1007500000",
                    },
                )
            ],
        }
    )

    report = format_report(collect_pipeline_times(redis_client, count=100))

    assert "TCP line -> raw Redis publish" in report
    assert "raw Redis -> validator starts" in report
    assert "validator start -> validated Redis" in report
    assert "latest tick age at VP publish" in report
    assert "source TCP -> VP publish age" in report
    assert "VP snapshot calculation" in report
    assert "VP snapshot start -> Redis" in report
    assert "p99=" in report
