"""Join strategy candidates to timestamped features and run the selected model.

The router reads both Redis streams in one event loop. A candidate is never
matched to "the latest" features: symbol, date, and time_s must all match.
TradeStation ``CurrentBar`` is retained as diagnostics but is not a stable
cross-study identifier. Features and candidates may arrive in either order.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
import json
import pickle
import time
from typing import Callable

import numpy as np
import torch

from config.setting import (
    REDIS1_CANDIDATE_STREAM,
    REDIS1_DECISION_STREAM,
    REDIS1_FEATURES_TRANSFORMER_STREAM,
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_ROUTER_READY_KEY,
    REDIS1_ROUTER_CANDIDATE_GROUP,
    REDIS1_ROUTER_CONSUMER,
)
from feat_files.canonical_features import FEATURE_NAMES
from inference.candidate_codec import candidate_from_redis_fields
from inference.candidate_contract import CandidateError, TradeCandidate
from inference.inference_engine import MLP
from inference.model_registry import enabled_model_settings
from netwo_files.redis_tool import get_redis_connection


BarKey = tuple[str, int, int]
Decision = dict[str, str]


def _feature_key(fields: dict[str, str]) -> BarKey:
    return (
        fields["symbol"],
        int(fields["date"]),
        int(fields["time_s"]),
    )


def _xread_has_entries(result: list) -> bool:
    """Return whether a Redis XREAD/XREADGROUP wrapper contains any entries."""
    return any(entries for _, entries in result)


class StrategyModel:
    """One model loaded once and reused for every candidate of its strategy."""

    def __init__(self, settings: dict) -> None:
        self.threshold = float(settings["threshold"])
        requested_device = settings.get("device", "cpu")
        if requested_device == "cuda" and not torch.cuda.is_available():
            raise ValueError("registry requests CUDA but CUDA is unavailable")
        self.device = torch.device(requested_device)
        with open(settings["scaler"], "rb") as handle:
            self.scaler = pickle.load(handle)
        with open(settings["config"], encoding="utf-8") as handle:
            config = json.load(handle)
        configured = config.get("feature_cols", list(FEATURE_NAMES))
        if list(configured) != list(FEATURE_NAMES):
            raise ValueError("model feature order differs from canonical features")
        self.model = MLP(input_dim=config["n_features"]).to(self.device)
        self.model.load_state_dict(
            torch.load(settings["model"], map_location=self.device)
        )
        self.model.eval()

    def infer(self, fields: dict[str, str]) -> tuple[bool, float]:
        values = np.array(
            [[float(fields[name]) for name in FEATURE_NAMES]], dtype=np.float32
        )
        scaled = self.scaler.transform(values).astype(np.float32)
        with torch.no_grad():
            probability = torch.sigmoid(
                self.model(torch.from_numpy(scaled).to(self.device))
            ).item()
        return probability >= self.threshold, probability


@dataclass
class _Pending:
    candidate: TradeCandidate
    deadline: float
    candidate_received_ns: int
    candidate_entry_id: str


class RouterCore:
    """I/O-free matching state, kept separate so race behavior is testable."""

    def __init__(
        self,
        models: dict[str, Callable[[dict[str, str]], tuple[bool, float]]],
        timeout_s: float = 0.25,
        max_features: int = 5_000,
    ) -> None:
        self.models = models
        self.timeout_s = timeout_s
        self.max_features = max_features
        self.features: OrderedDict[BarKey, dict[str, str]] = OrderedDict()
        self.pending: dict[BarKey, list[_Pending]] = {}
        self.seen: set[str] = set()

    def on_feature(self, fields: dict[str, str]) -> list[Decision]:
        key = _feature_key(fields)
        self.features[key] = fields
        self.features.move_to_end(key)
        while len(self.features) > self.max_features:
            self.features.popitem(last=False)
        waiting = self.pending.pop(key, [])
        return [
            self._infer(
                item.candidate,
                fields,
                item.candidate_received_ns,
                item.candidate_entry_id,
            )
            for item in waiting
        ]

    def on_candidate(
        self,
        candidate: TradeCandidate,
        now: float | None = None,
        received_ns: int | None = None,
        entry_id: str = "",
    ) -> list[Decision]:
        candidate_received_ns = time.time_ns() if received_ns is None else received_ns
        if candidate.candidate_id in self.seen:
            return []
        self.seen.add(candidate.candidate_id)
        if candidate.strategy_id not in self.models:
            return [
                self._decision(
                    candidate,
                    "unknown_strategy",
                    False,
                    0.0,
                    candidate_received_ns=candidate_received_ns,
                    candidate_entry_id=entry_id,
                )
            ]
        fields = self.features.get(candidate.bar_key)
        if fields is not None:
            return [
                self._infer(candidate, fields, candidate_received_ns, entry_id)
            ]
        current = time.monotonic() if now is None else now
        self.pending.setdefault(candidate.bar_key, []).append(
            _Pending(
                candidate,
                current + self.timeout_s,
                candidate_received_ns,
                entry_id,
            )
        )
        return []

    def expire(self, now: float | None = None) -> list[Decision]:
        current = time.monotonic() if now is None else now
        decisions: list[Decision] = []
        for key in list(self.pending):
            keep = []
            for item in self.pending[key]:
                if item.deadline <= current:
                    decisions.append(
                        self._decision(
                            item.candidate,
                            "missing_features",
                            False,
                            0.0,
                            candidate_received_ns=item.candidate_received_ns,
                            candidate_entry_id=item.candidate_entry_id,
                        )
                    )
                else:
                    keep.append(item)
            if keep:
                self.pending[key] = keep
            else:
                del self.pending[key]
        return decisions

    def _infer(
        self,
        candidate: TradeCandidate,
        fields: dict[str, str],
        candidate_received_ns: int,
        candidate_entry_id: str,
    ) -> Decision:
        features_matched_ns = time.time_ns()
        inference_started_ns = time.time_ns()
        try:
            approved, probability = self.models[candidate.strategy_id](fields)
            inference_finished_ns = time.time_ns()
            return self._decision(
                candidate,
                "ok",
                approved,
                probability,
                candidate_received_ns=candidate_received_ns,
                features_matched_ns=features_matched_ns,
                inference_started_ns=inference_started_ns,
                inference_finished_ns=inference_finished_ns,
                candidate_entry_id=candidate_entry_id,
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            inference_finished_ns = time.time_ns()
            return self._decision(
                candidate,
                "inference_error",
                False,
                0.0,
                str(exc),
                candidate_received_ns,
                features_matched_ns,
                inference_started_ns,
                inference_finished_ns,
                candidate_entry_id,
            )

    @staticmethod
    def _decision(
        candidate: TradeCandidate,
        status: str,
        approved: bool,
        probability: float,
        reason: str = "",
        candidate_received_ns: int | None = None,
        features_matched_ns: int | None = None,
        inference_started_ns: int | None = None,
        inference_finished_ns: int | None = None,
        candidate_entry_id: str = "",
    ) -> Decision:
        decision_created_ns = time.time_ns()
        received_ns = decision_created_ns if candidate_received_ns is None else candidate_received_ns

        def elapsed_ms(start_ns: int | None, end_ns: int | None) -> str:
            if start_ns is None or end_ns is None:
                return ""
            return f"{max(0, end_ns - start_ns) / 1_000_000:.3f}"

        return {
            "strategy_id": candidate.strategy_id,
            "instance_id": candidate.instance_id,
            "candidate_id": candidate.candidate_id,
            "symbol": candidate.symbol,
            "date": str(candidate.date),
            "time_s": str(candidate.time_s),
            "bar_num": str(candidate.bar_num),
            "direction": str(candidate.direction),
            "status": status,
            "approved": "1" if approved else "0",
            "prob": repr(probability),
            "reason": reason.replace(",", ";").replace("\n", " ")[:200],
            "candidate_received_ns": str(received_ns),
            "features_matched_ns": "" if features_matched_ns is None else str(features_matched_ns),
            "inference_started_ns": "" if inference_started_ns is None else str(inference_started_ns),
            "inference_finished_ns": "" if inference_finished_ns is None else str(inference_finished_ns),
            "decision_created_ns": str(decision_created_ns),
            "feature_wait_ms": elapsed_ms(received_ns, features_matched_ns),
            "inference_ms": elapsed_ms(inference_started_ns, inference_finished_ns),
            "router_total_ms": elapsed_ms(received_ns, decision_created_ns),
            "_candidate_entry_id": candidate_entry_id,
        }


def _publish(redis_client, decisions: list[Decision]) -> None:
    for decision in decisions:
        decision_published_ns = time.time_ns()
        decision["decision_published_ns"] = str(decision_published_ns)
        decision["router_to_publish_ms"] = (
            f"{max(0, decision_published_ns - int(decision['decision_created_ns'])) / 1_000_000:.3f}"
        )
        xadd_started_ns = time.perf_counter_ns()
        public_decision = {
            name: value for name, value in decision.items() if not name.startswith("_")
        }
        redis_client.xadd(
            REDIS1_DECISION_STREAM,
            public_decision,
            maxlen=5_000,
            approximate=True,
        )
        candidate_entry_id = decision.get("_candidate_entry_id", "")
        if candidate_entry_id:
            redis_client.xack(
                REDIS1_CANDIDATE_STREAM,
                REDIS1_ROUTER_CANDIDATE_GROUP,
                candidate_entry_id,
            )
        redis_xadd_ms = (time.perf_counter_ns() - xadd_started_ns) / 1_000_000
        print(
            f"{datetime.now().isoformat(timespec='milliseconds')} "
            f"[router] {decision['strategy_id']} "
            f"instance={decision['instance_id']} "
            f"candidate={decision['candidate_id']} "
            f"date={decision['date']} time_s={decision['time_s']} "
            f"status={decision['status']} "
            f"approved={decision['approved']} "
            f"feature_wait_ms={decision['feature_wait_ms'] or 'n/a'} "
            f"inference_ms={decision['inference_ms'] or 'n/a'} "
            f"router_total_ms={decision['router_total_ms']} "
            f"redis_xadd_ms={redis_xadd_ms:.3f}"
        )


def run(timeout_ms: int = 250) -> None:
    torch.set_num_threads(1)
    strategy_models = enabled_model_settings()
    runtimes = {
        strategy_id: StrategyModel(settings)
        for strategy_id, settings in strategy_models.items()
    }
    core = RouterCore(
        {strategy_id: runtime.infer for strategy_id, runtime in runtimes.items()},
        timeout_s=timeout_ms / 1_000,
    )
    redis_client = get_redis_connection(
        REDIS1_HOST, REDIS1_PORT, REDIS1_CANDIDATE_STREAM
    )
    try:
        redis_client.xgroup_create(
            REDIS1_CANDIDATE_STREAM,
            REDIS1_ROUTER_CANDIDATE_GROUP,
            id="$",
            mkstream=True,
        )
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise

    recent_features = redis_client.xrevrange(
        REDIS1_FEATURES_TRANSFORMER_STREAM, count=core.max_features
    )
    for _, fields in reversed(recent_features):
        try:
            core.on_feature(fields)
        except (KeyError, TypeError, ValueError):
            continue

    last_feature_id = "$"
    pending_candidate_id = "0-0"
    reading_pending = True
    redis_client.set(REDIS1_ROUTER_READY_KEY, "1")
    print(
        f"[router] strategies={','.join(runtimes)} "
        f"feature_timeout_ms={timeout_ms}"
    )
    while True:
        feature_results = redis_client.xread(
            {REDIS1_FEATURES_TRANSFORMER_STREAM: last_feature_id},
            count=100,
            block=1,
        )
        candidate_results = redis_client.xreadgroup(
            REDIS1_ROUTER_CANDIDATE_GROUP,
            REDIS1_ROUTER_CONSUMER,
            {
                REDIS1_CANDIDATE_STREAM: (
                    pending_candidate_id if reading_pending else ">"
                )
            },
            count=100,
            block=25,
        )
        decisions: list[Decision] = []
        for stream, entries in feature_results:
            for entry_id, fields in entries:
                last_feature_id = entry_id
                try:
                    decisions.extend(core.on_feature(fields))
                except (KeyError, ValueError) as exc:
                    print(f"[router] rejected {stream} entry: {exc}")
        if reading_pending and not _xread_has_entries(candidate_results):
            reading_pending = False
        for stream, entries in candidate_results:
            for entry_id, fields in entries:
                if reading_pending:
                    pending_candidate_id = entry_id
                try:
                    candidate = candidate_from_redis_fields(fields)
                    if candidate.candidate_id in core.seen:
                        redis_client.xack(
                            REDIS1_CANDIDATE_STREAM,
                            REDIS1_ROUTER_CANDIDATE_GROUP,
                            entry_id,
                        )
                        continue
                    received_ns = int(
                        fields.get("candidate_received_ns", time.time_ns())
                    )
                    decisions.extend(
                        core.on_candidate(
                            candidate,
                            received_ns=received_ns,
                            entry_id=entry_id,
                        )
                    )
                except (CandidateError, KeyError, ValueError) as exc:
                    print(f"[router] rejected {stream} entry: {exc}")
                    redis_client.xack(
                        REDIS1_CANDIDATE_STREAM,
                        REDIS1_ROUTER_CANDIDATE_GROUP,
                        entry_id,
                    )
        decisions.extend(core.expire())
        _publish(redis_client, decisions)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-timeout-ms", type=int, default=250)
    args = parser.parse_args()
    run(args.feature_timeout_ms)


if __name__ == "__main__":
    main()
