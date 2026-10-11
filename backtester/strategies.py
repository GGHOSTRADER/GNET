"""Compatibility imports only; all strategy logic lives in strategies/."""
from strategies.base import EntryStrategy
from strategies.ma_cross import MACrossParameters, MACrossStrategy
from strategies.registry import STRATEGIES, StrategySpec, build_strategy


__all__ = ["EntryStrategy", "MACrossParameters", "MACrossStrategy", "STRATEGIES", "StrategySpec", "build_strategy"]










