"""Independent strategy plugins. No backtester or live-service dependency."""

from strategies.base import EntryStrategy
from strategies.registry import StrategySpec, build_strategy

__all__ = ["EntryStrategy", "StrategySpec", "build_strategy"]
