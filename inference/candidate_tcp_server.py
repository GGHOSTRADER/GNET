"""Receive candidates from every TradeStation strategy window on TCP 9012."""

from __future__ import annotations

import socketserver
import time
from datetime import datetime

from config.setting import (
    REDIS1_CANDIDATE_STREAM,
    REDIS1_HOST,
    REDIS1_PORT,
    TCP_CANDIDATE_HOST,
    TCP_CANDIDATE_PORT,
)
from inference.candidate_codec import candidate_to_redis_fields, parse_candidate_line
from inference.candidate_contract import CandidateError
from netwo_files.redis_tool import get_redis_connection


class _CandidateHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        redis_client = get_redis_connection(
            REDIS1_HOST, REDIS1_PORT, REDIS1_CANDIDATE_STREAM
        )
        for raw_line in self.rfile:
            try:
                candidate = parse_candidate_line(raw_line.decode("utf-8").strip())
            except (UnicodeDecodeError, CandidateError) as exc:
                print(f"[candidate_server] rejected: {exc}")
                continue
            candidate_received_ns = time.time_ns()
            fields = candidate_to_redis_fields(candidate)
            fields["candidate_received_ns"] = str(candidate_received_ns)
            redis_client.xadd(
                REDIS1_CANDIDATE_STREAM,
                fields,
                maxlen=5_000,
                approximate=True,
            )
            print(
                f"~ {datetime.now().isoformat(timespec='milliseconds')} "
                f"[candidate_server] {candidate.strategy_id} "
                f"instance={candidate.instance_id} "
                f"candidate={candidate.candidate_id} "
                f"date={candidate.date} time_s={candidate.time_s} "
                f"bar={candidate.bar_num}"
            )


class _ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run() -> None:
    print(
        "[candidate_server] Ready\n"
        f"  TCP Host: {TCP_CANDIDATE_HOST}\n"
        f"  TCP Port: {TCP_CANDIDATE_PORT}\n"
        f"  Redis Host: {REDIS1_HOST}\n"
        f"  Redis Port: {REDIS1_PORT}\n"
        f"  Redis Stream: {REDIS1_CANDIDATE_STREAM}\n\n"
        "[candidate_server] Purpose: receives candidate.\n"
    )
    with _ThreadingServer(
        (TCP_CANDIDATE_HOST, TCP_CANDIDATE_PORT), _CandidateHandler
    ) as server:
        server.serve_forever()


if __name__ == "__main__":
    run()
