"""Run GNET Backtester from an explicit JSON experiment configuration."""
from __future__ import annotations

import argparse
from pathlib import Path
import json

from backtester.config import Policy, atomic_json, load_config
from backtester.data import prepare, source_inventory
from backtester.results_report import write_catalog
from backtester.workers import Evaluator


def run(config, *, resume=False, prepare_only=False, report_only=False, confirm=False):
    config.validate()
    sources, identity = source_inventory(config)
    root = Path(config.output)
    run_path = root / "run.json"
    if root.exists() and not (resume or report_only or confirm):
        raise FileExistsError("output already exists; use --resume or choose a new output")
    if run_path.exists():
        previous = json.loads(run_path.read_text())
        if previous["identity"] != identity:
            raise ValueError("input/configuration/code identity changed; use a new output directory")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("output contains unrelated files and has no backtester run manifest")
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(run_path, {"identity": identity, "config": config.dictionary(), "sources": sources})
    metadata = prepare(config, sources, identity)
    if prepare_only:
        return {"prepared": str(root / "prepared"), "ticks": metadata["ticks"], "signals": metadata["signal_counts"]}
    if confirm:
        if not config.confirmation_start:
            raise ValueError("set confirmation_start before starting the experiment")
        result_path = root / "confirmation.json"
        if result_path.exists():
            return json.loads(result_path.read_text())
        frozen_path = root / "confirmation_plan.json"
        if frozen_path.exists():
            selections = json.loads(frozen_path.read_text())["selections"]
        else:
            selections = json.loads((root / "selections.json").read_text())
            atomic_json(frozen_path, {"identity": identity, "selections": selections})
        results = []
        for selection in selections:
            row = selection["selection"]
            if row is None:
                continue
            policy = Policy(row["profit_ticks"], row["stop_ticks"], row["hold_seconds"])
            with Evaluator(config, selection["bar_spec"], "confirmation") as evaluator:
                results.extend(evaluator.evaluate_policies([policy]))
        result = {"identity": identity, "frozen_selections": selections, "results": results,
                  "boundary_convention": "confirmation starts flat; indicators retain causal prior history",
                  "backtesting_results": write_catalog(config)}
        atomic_json(result_path, result)
        return result
    if (root / "confirmation_plan.json").exists() and not report_only:
        raise ValueError("confirmation has started; this run's search is frozen")
    selections = []
    for spec in config.bars:
        if config.execution_mode == "preset":
            if report_only:
                path = root / "policies" / spec.key / "development" / config.preset_policy.key / "summary.json"
                row = json.loads(path.read_text())
            else:
                with Evaluator(config, spec.key) as evaluator:
                    row = evaluator.evaluate_policies([config.preset_policy])[0]
            selection = {"bar_spec": spec.key, "selection": row,
                         "selection_rule": "explicit preset; no search or ranking"}
        else:
            from backtester.exit_analyzer import ExitAnalyzer
            analyzer = ExitAnalyzer(config, spec.key)
            if report_only:
                selection = analyzer.run(report_only=True)
            else:
                with Evaluator(config, spec.key) as evaluator:
                    selection = analyzer.run(evaluator)
        if selection is not None:
            selections.append(selection)
    atomic_json(root / "selections.json", selections)
    return {"output": str(root), "ticks": metadata["ticks"], "reports": selections,
            "execution_mode": config.execution_mode, "backtesting_results": write_catalog(config)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--workers", type=int)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prepare-only", action="store_true")
    group.add_argument("--report-only", action="store_true")
    group.add_argument("--confirm", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.workers is not None:
        config.workers = args.workers
    try:
        result = run(config, resume=args.resume, prepare_only=args.prepare_only,
                     report_only=args.report_only, confirm=args.confirm)
    except KeyboardInterrupt:
        print("Stopped. Completed policy results remain on disk; resume with the same configuration.")
        raise SystemExit(130)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
