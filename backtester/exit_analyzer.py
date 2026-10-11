"""Optional exit-search coordinator; owns search state and comparison HTML."""
from pathlib import Path
import json
import time

from backtester.config import atomic_json
from backtester.report import write_report
from backtester.search import adaptive_search


class ExitAnalyzer:
    def __init__(self, config, bar_key):
        self.config, self.bar_key = config, bar_key
        self.state_path = Path(config.output) / "search" / f"{bar_key}.json"

    def run(self, evaluate=None, *, report_only=False):
        if report_only:
            state = json.loads(self.state_path.read_text())
            rows = [{k: v for k, v in row.items() if k != "coordinate"} for row in state["evaluated"]]
            reason = state["stop_reason"]
        else:
            if evaluate is None:
                raise ValueError("exit analysis needs a backtest evaluator")
            started = time.monotonic()

            def logged_evaluate(points):
                rows = evaluate(points)
                print(f"{self.bar_key}: finished {len(points)} policies; elapsed {time.monotonic() - started:.1f}s", flush=True)
                return rows

            results, _, reason = adaptive_search(
                self.config, logged_evaluate, lambda state: atomic_json(self.state_path, state))
            rows = list(results.values())
        return write_report(self.config, self.bar_key, rows, reason) if rows else None
