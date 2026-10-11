"""Explicit experiment configuration; paths are relative to the JSON file."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import hashlib
import json
import math

from strategies import StrategySpec


@dataclass(frozen=True)
class BarSpec:
    kind: str = "time"
    size: int = 30

    def __post_init__(self):
        if self.kind not in ("time", "tick", "volume") or type(self.size) is not int or self.size < 1:
            raise ValueError("bars require kind=time/tick/volume and a positive integer size")

    @property
    def key(self):
        return f"{self.kind}_{self.size}"


@dataclass(frozen=True)
class Policy:
    profit_ticks: int
    stop_ticks: int
    hold_seconds: int

    def __post_init__(self):
        if any(type(x) is not int or x < 1 for x in (self.profit_ticks, self.stop_ticks, self.hold_seconds)):
            raise ValueError("policy distances and holding time must be positive integers")

    @property
    def key(self):
        return f"pt{self.profit_ticks}_sl{self.stop_ticks}_h{self.hold_seconds}"


@dataclass
class ResultsSpec:
    initial_capital: float | None = None
    equity_sample_seconds: int = 60
    sessions_per_year: int = 252
    risk_free_per_session: float = 0.0
    effective_trials: float | None = None
    trial_sharpe_variance: float | None = None
    trial_history_note: str | None = None

    def validate(self):
        if self.initial_capital is not None and (not math.isfinite(self.initial_capital) or self.initial_capital <= 0):
            raise ValueError("initial_capital must be finite and positive")
        for name in ("equity_sample_seconds", "sessions_per_year"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not math.isfinite(self.risk_free_per_session):
            raise ValueError("risk_free_per_session must be finite")
        evidence = (self.effective_trials, self.trial_sharpe_variance, self.trial_history_note)
        if any(x is not None for x in evidence):
            if (any(x is None for x in evidence) or not math.isfinite(self.effective_trials)
                    or self.effective_trials <= 1 or not math.isfinite(self.trial_sharpe_variance)
                    or self.trial_sharpe_variance < 0 or not str(self.trial_history_note).strip()):
                raise ValueError("DSR requires effective_trials > 1, nonnegative session-Sharpe variance and trial_history_note")
        return self


@dataclass
class Config:
    tick_root: str
    output: str
    start_session: str
    end_session: str
    bars: list[BarSpec] = field(default_factory=lambda: [BarSpec()])
    timezone: str = "America/New_York"
    strategy: StrategySpec = field(default_factory=StrategySpec)
    execution_mode: str = "sweep"
    preset_policy: Policy | None = None
    results: ResultsSpec = field(default_factory=ResultsSpec)
    session_open: str = "18:00:00"
    session_close: str = "17:00:00"
    session_exit: str = "flatten"
    flatten_lead_seconds: int = 60
    session_close_overrides: dict[str, str] = field(default_factory=dict)
    confirmation_start: str | None = None
    round_trip_cost: float = 6.48
    slippage_ticks: float = 0.0
    max_entry_delay_seconds: float = 30.0
    max_exit_delay_seconds: float = 30.0
    max_tick_gap_seconds: float | None = None
    profits: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 6, 8, 12, 16])
    stops: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 6, 8, 12, 16])
    holds: list[int] = field(default_factory=lambda: [30, 60, 120, 300])
    workers: int = 4
    policy_batch_size: int = 4
    max_evaluations: int = 64
    max_seconds: float = 3600.0
    patience: int = 2
    jump_factor: int = 3
    failed_jumps: int = 2
    search_regions: int = 3
    improvement_tolerance: float = 0.0
    min_trades: int = 10
    max_drawdown: float | None = None
    time_blocks: int = 3
    region_min_positive_blocks: int = 2

    def validate(self):
        from datetime import date, time
        if date.fromisoformat(self.start_session) > date.fromisoformat(self.end_session):
            raise ValueError("start_session must be at or before end_session")
        if self.confirmation_start and not (self.start_session < self.confirmation_start <= self.end_session):
            raise ValueError("confirmation_start must leave both development and confirmation dates")
        time.fromisoformat(self.session_open)
        time.fromisoformat(self.session_close)
        for day, close in self.session_close_overrides.items():
            date.fromisoformat(day)
            time.fromisoformat(close)
        if not isinstance(self.strategy, StrategySpec):
            raise ValueError("strategy must be a StrategySpec")
        self.strategy.validate()
        if self.execution_mode not in ("sweep", "preset"):
            raise ValueError("execution_mode must be sweep or preset")
        if self.execution_mode == "preset" and not isinstance(self.preset_policy, Policy):
            raise ValueError("preset mode requires a preset_policy")
        if self.execution_mode == "sweep" and self.preset_policy is not None:
            raise ValueError("preset_policy is only used in preset mode")
        if not isinstance(self.results, ResultsSpec):
            raise ValueError("results must be a ResultsSpec")
        self.results.validate()
        if not self.bars or len({b.key for b in self.bars}) != len(self.bars):
            raise ValueError("choose at least one unique bar specification")
        for axis in (self.profits, self.stops, self.holds):
            if not axis or any(type(x) is not int or x < 1 for x in axis) or axis != sorted(set(axis)):
                raise ValueError("search axes must be sorted unique positive integers")
        for name in ("workers", "policy_batch_size", "max_evaluations", "patience", "failed_jumps", "search_regions", "time_blocks", "jump_factor", "min_trades"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.jump_factor < 2 or self.min_trades < 1:
            raise ValueError("jump_factor >= 2 and min_trades >= 1 required")
        for name in ("round_trip_cost", "slippage_ticks", "max_entry_delay_seconds", "max_exit_delay_seconds", "improvement_tolerance", "flatten_lead_seconds"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.max_seconds <= 0 or not math.isfinite(self.max_seconds):
            raise ValueError("max_seconds must be finite and positive")
        for value in (self.max_tick_gap_seconds, self.max_drawdown):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError("optional gap/drawdown limits must be finite and positive")
        if self.session_exit not in ("flatten", "carry"):
            raise ValueError("session_exit must be flatten or carry")
        if type(self.region_min_positive_blocks) is not int or not 0 <= self.region_min_positive_blocks <= self.time_blocks:
            raise ValueError("region_min_positive_blocks must be between zero and time_blocks")
        return self

    def dictionary(self):
        return asdict(self)

    def identity(self):
        data = self.dictionary()
        for key in ("output", "workers", "policy_batch_size", "max_evaluations", "max_seconds"):
            data.pop(key)
        return data


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if {"fast", "slow", "reset_ma_each_session"} & data.keys():
        raise ValueError("MA settings belong under strategy.parameters (fast, slow, reset_each_session), not at the engine root")
    strategy = data.get("strategy", {})
    if not isinstance(strategy, dict):
        raise ValueError("strategy must be an object with name and parameters")
    data["strategy"] = StrategySpec(**strategy)
    data["results"] = ResultsSpec(**data.get("results", {}))
    if data.get("preset_policy") is not None:
        data["preset_policy"] = Policy(**data["preset_policy"])
    data["bars"] = [BarSpec(**b) for b in data.get("bars", [{"kind": "time", "size": 30}])]
    for key in ("tick_root", "output"):
        data[key] = str((path.parent / data[key]).resolve())
    return Config(**data).validate()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)
