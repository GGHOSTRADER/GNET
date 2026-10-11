"""Deterministic bounded exploration, neighborhood refinement, and jump probes."""
from __future__ import annotations

from itertools import product
import math
import time

from backtester.config import Policy


def adaptive_search(config, evaluate, checkpoint=lambda state: None):
    """evaluate receives index coordinates and returns summaries in that order.

    Completed batches are replayable from cached policy summaries. Budget
    checks happen between batches; in-flight workers finish their current batch.
    """
    axes = (config.profits, config.stops, config.holds)
    shape = tuple(len(axis) for axis in axes)
    results, trace = {}, []
    started = time.monotonic()
    stop = None

    def score(point):
        value = results[point].get("score")
        return -math.inf if value is None else float(value)

    def snapshot(regions):
        checkpoint({"evaluated": [{"coordinate": list(p), **row} for p, row in results.items()],
                    "regions": regions, "trace": trace, "stop_reason": stop})

    def sample(points):
        nonlocal stop
        pending = [p for p in sorted(set(points)) if p not in results]
        while pending:
            remaining = config.max_evaluations - len(results)
            if remaining <= 0:
                stop = "evaluation_budget"
                return False
            if time.monotonic() - started >= config.max_seconds:
                stop = "wall_time_budget"
                return False
            batch = pending[:min(remaining, config.workers * config.policy_batch_size)]
            del pending[:len(batch)]
            rows = evaluate(batch)
            if len(rows) != len(batch):
                raise ValueError("worker results do not match submitted policy batch")
            results.update(zip(batch, rows))
            trace.append({"action": "evaluate", "coordinates": [list(p) for p in batch]})
            snapshot([])
        return True

    seeds = list(product(*[sorted({0, n - 1}) for n in shape]))
    seeds.append(tuple(n // 2 for n in shape))
    complete = sample(seeds)
    ranked = sorted(results, key=lambda p: (-score(p), p))
    regions = [{"center": list(p), "radius": 1, "bad_rounds": 0, "failed_probes": 0,
                "mode": "local", "active": True} for p in ranked[:config.search_regions]]
    while complete and any(r["active"] for r in regions):
        for region in regions:
            if not region["active"]:
                continue
            center = tuple(region["center"])
            radius = region["radius"]
            neighborhood = [tuple(center[d] + move[d] * radius for d in range(3))
                            for move in product((-1, 0, 1), repeat=3) if any(move)]
            neighborhood = [p for p in neighborhood if all(0 <= p[d] < shape[d] for d in range(3))]
            complete = sample(neighborhood)
            if not complete:
                break
            candidates = [center, *neighborhood]
            best = min(candidates, key=lambda p: (-score(p), p))
            improved = score(best) > score(center) + config.improvement_tolerance
            trace.append({"action": region["mode"], "center": list(center), "radius": radius,
                          "improved": improved, "best": list(best)})
            if improved:
                region.update(center=list(best), radius=1, bad_rounds=0, failed_probes=0, mode="local")
            elif region["mode"] == "jump":
                region["failed_probes"] += 1
                if region["failed_probes"] >= config.failed_jumps:
                    region["active"] = False
                else:
                    region["radius"] *= config.jump_factor
            else:
                region["bad_rounds"] += 1
                if region["bad_rounds"] >= config.patience:
                    region.update(mode="jump", radius=radius * config.jump_factor)
                else:
                    region["radius"] += 1
            snapshot(regions)
    if stop is None:
        stop = "domain_evaluated" if len(results) == math.prod(shape) else "regions_exhausted"
    snapshot(regions)
    return results, trace, stop


def coordinate_policy(config, point):
    return Policy(config.profits[point[0]], config.stops[point[1]], config.holds[point[2]])
