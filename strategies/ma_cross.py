"""Standalone SMA-crossover entry rule and its strategy-specific parameters."""
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class MACrossParameters:
    fast: int = 9
    slow: int = 18
    reset_each_session: bool = False

    def __post_init__(self):
        if type(self.fast) is not int or type(self.slow) is not int or not 1 <= self.fast < self.slow:
            raise ValueError("ma_cross requires integer lengths: 1 <= fast < slow")
        if type(self.reset_each_session) is not bool:
            raise ValueError("ma_cross reset_each_session must be a boolean")


class MACrossStrategy:
    def __init__(self, **parameters):
        self.parameters = MACrossParameters(**parameters)
        self.values = deque(maxlen=self.parameters.slow)
        self.previous = None

    def on_session_start(self):
        if self.parameters.reset_each_session:
            self.values.clear()
            self.previous = None

    def on_bar(self, bar):
        self.values.append(bar["close"])
        if len(self.values) < self.parameters.slow:
            return False
        values = list(self.values)
        difference = (sum(values[-self.parameters.fast:]) / self.parameters.fast
                      - sum(values) / self.parameters.slow)
        crossed = self.previous is not None and self.previous <= 0 < difference
        self.previous = difference
        return crossed
