"""Validated contract for a primary strategy's proposed trade."""

from __future__ import annotations

from dataclasses import dataclass
import re


class CandidateError(ValueError):
    """A candidate cannot safely enter the routing pipeline."""


_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_SYMBOL = re.compile(r"^[A-Za-z0-9@._-]{1,64}$")


@dataclass(frozen=True)
class TradeCandidate:
    strategy_id: str
    instance_id: str
    candidate_id: str
    symbol: str
    date: int
    time_s: int
    bar_num: int
    direction: int

    @property
    def bar_key(self) -> tuple[str, int, int]:
        return self.symbol, self.date, self.time_s


def validate_candidate(candidate: TradeCandidate) -> TradeCandidate:
    for name in ("strategy_id", "instance_id", "candidate_id"):
        value = getattr(candidate, name)
        if not _IDENTIFIER.fullmatch(value):
            raise CandidateError(f"invalid {name}: {value!r}")
    if not _SYMBOL.fullmatch(candidate.symbol):
        raise CandidateError(f"invalid symbol: {candidate.symbol!r}")
    if candidate.date <= 0:
        raise CandidateError("date must be positive")
    if not 0 <= candidate.time_s <= 86_399:
        raise CandidateError("time_s must be between 0 and 86399")
    if candidate.bar_num < 0:
        raise CandidateError("bar_num must be non-negative")
    if candidate.direction not in (-1, 1):
        raise CandidateError("direction must be -1 or 1")
    return candidate
