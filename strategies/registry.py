"""Resolve strategy names to separately imported implementations."""
from dataclasses import dataclass, field
from importlib import import_module

from strategies.base import EntryStrategy


STRATEGIES = {"ma_cross": "strategies.ma_cross:MACrossStrategy"}


@dataclass
class StrategySpec:
    name: str = "ma_cross"
    parameters: dict = field(default_factory=dict)

    def validate(self):
        build_strategy(self)
        return self


def build_strategy(spec: StrategySpec) -> EntryStrategy:
    if not isinstance(spec, StrategySpec) or not isinstance(spec.name, str) or spec.name not in STRATEGIES:
        raise ValueError("unknown entry strategy; registered strategies: " + ", ".join(sorted(STRATEGIES)))
    if not isinstance(spec.parameters, dict):
        raise ValueError("strategy.parameters must be an object")
    factory = STRATEGIES[spec.name]
    if isinstance(factory, str):
        module, separator, attribute = factory.partition(":")
        if not separator or not module or not attribute:
            raise ValueError("strategy registration must be module:Class")
        factory = getattr(import_module(module), attribute)
    try:
        strategy = factory(**spec.parameters)
    except TypeError as exc:
        raise ValueError(f"invalid parameters for strategy {spec.name}: {exc}") from exc
    if not all(callable(getattr(strategy, method, None)) for method in ("on_session_start", "on_bar")):
        raise ValueError("strategy must implement on_session_start() and on_bar(bar)")
    return strategy
