"""Canonical event-aware validation splitters for financial ML."""

from .event_intervals import EventIntervals, ValidationSplit
from .purged_walk_forward import PurgedWalkForward, purged_chronological_holdout
from .cpcv import CombinatorialPurgedCrossValidation

__all__ = [
    "CombinatorialPurgedCrossValidation",
    "EventIntervals",
    "PurgedWalkForward",
    "ValidationSplit",
    "purged_chronological_holdout",
]
