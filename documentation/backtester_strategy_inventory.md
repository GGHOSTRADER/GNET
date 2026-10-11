# Strategy inventory

[Human guide](guides/BACKTESTER_GUIDE.md) · [Agent runbook](guides/BACKTESTER_AGENT_GUIDE.md)

The executable inventory is [strategies/registry.py](../strategies/registry.py).
It maps a configuration name to an imported strategy implementation. The
backtester does not contain MA lengths or crossover rules internally.

## What is available now

| Selectable name | Rule | Parameters and defaults | Source |
|---|---|---|---|
| `ma_cross` | Buy candidate when the fast simple moving average crosses from at/below to above the slow average on a completed bar | `fast=9`, `slow=18`, `reset_each_session=false` | [MA crossover](../strategies/ma_cross.py) |

There is **one registered strategy**, not five. Other primary strategies,
short entries and strategy-native exits are not implemented yet.

Lengths must be integers with `1 <= fast < slow`. With session reset disabled,
MA state can carry between sessions; the preparation layer still resets it
when the source-vintage boundary changes. A signal is a candidate, not a fill.
[Signal construction](../backtester/signals.py) finds the next eligible tick;
[replay](../backtester/replay.py) decides whether it can enter, including
whether that exit policy already has an open position.

## Select and run

Put this block in the experiment JSON, not in the bar-builder configuration:

```json
"strategy": {
  "name": "ma_cross",
  "parameters": {"fast": 9, "slow": 18, "reset_each_session": false}
}
```

Use the complete [preset example](../config/backtester.preset.example.json)
or [exit-search example](../config/backtester.example.json). Select exit behavior
separately: `execution_mode="preset"` plus `preset_policy`, or
`execution_mode="sweep"` plus profit/stop/hold search axes. The current strategy
plugin supplies entry logic only; it does not override those exits.

```powershell
Set-Location 'C:\Users\g_med\python_new\GNET'
.\.venv\Scripts\python.exe -m scripts.backtester_inventory strategies
.\.venv\Scripts\python.exe -m scripts.backtester_inventory strategies --json
.\.venv\Scripts\python.exe -m backtester.run --config config/backtester.preset.example.json
```

Run the last command only after selecting a fresh output folder, or use
`--resume` for the same existing experiment.

## Adding a strategy to the inventory

The [strategy interface](../strategies/base.py) defines `on_session_start()`
and `on_bar(bar)`. A new implementation belongs under `strategies/`, owns and
validates its own parameters, and must use only information available when
that bar closes. Register its name and `module:Class` in the registry, add
causality/trigger tests, and update this inventory. The factory
`build_strategy()` resolves the name and checks the required methods.

This is a plugin boundary, not a requirement for a large strategy class.
Keeping a small rule in its own implementation file prevents the backtester
from accumulating strategy-specific conditions. Adding code in this package
changes run identity; use a new output directory for the changed implementation.
