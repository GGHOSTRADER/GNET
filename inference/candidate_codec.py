"""TCP and Redis codecs for strategy candidates."""

from __future__ import annotations

from inference.candidate_contract import CandidateError, TradeCandidate, validate_candidate


def parse_candidate_line(line: str) -> TradeCandidate:
    """Parse strategy, instance, candidate, symbol, and exact bar identity."""
    parts = [part.strip() for part in line.split(",")]
    if len(parts) != 8:
        raise CandidateError(f"expected 8 fields, received {len(parts)}")
    try:
        candidate = TradeCandidate(
            strategy_id=parts[0],
            instance_id=parts[1],
            candidate_id=parts[2],
            symbol=parts[3],
            date=int(parts[4]),
            time_s=int(parts[5]),
            bar_num=int(parts[6]),
            direction=int(parts[7]),
        )
    except ValueError as exc:
        raise CandidateError("candidate contains a non-integer numeric field") from exc
    return validate_candidate(candidate)


def candidate_to_redis_fields(candidate: TradeCandidate) -> dict[str, str]:
    return {
        "strategy_id": candidate.strategy_id,
        "instance_id": candidate.instance_id,
        "candidate_id": candidate.candidate_id,
        "symbol": candidate.symbol,
        "date": str(candidate.date),
        "time_s": str(candidate.time_s),
        "bar_num": str(candidate.bar_num),
        "direction": str(candidate.direction),
    }


def candidate_from_redis_fields(fields: dict[str, str]) -> TradeCandidate:
    return parse_candidate_line(
        ",".join(
            fields[name]
            for name in (
                "strategy_id", "instance_id", "candidate_id", "symbol", "date",
                "time_s", "bar_num", "direction",
            )
        )
    )
