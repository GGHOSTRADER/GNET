"""Parallel policies, each evaluated against the complete chronological tape."""
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import os

from backtester.replay import evaluate_batch
from backtester.search import coordinate_policy


def initialize_worker():
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[name] = "1"
    try:
        from threadpoolctl import threadpool_limits
        threadpool_limits(limits=1)
    except ImportError:
        pass


class Evaluator:
    def __init__(self, config, bar_key, phase="development"):
        self.config, self.bar_key, self.phase = config, bar_key, phase
        self.pool = None

    def __enter__(self):
        if self.config.workers > 1:
            self.pool = ProcessPoolExecutor(self.config.workers, mp_context=get_context("spawn"), initializer=initialize_worker)
        return self

    def __exit__(self, *args):
        if self.pool is not None:
            self.pool.shutdown(wait=True, cancel_futures=True)

    def __call__(self, coordinates):
        policies = [coordinate_policy(self.config, point) for point in coordinates]
        return self.evaluate_policies(policies)

    def evaluate_policies(self, policies):
        """Explicit policies need not belong to an exit-search grid."""
        size = self.config.policy_batch_size
        tasks = [(self.config, self.bar_key, policies[i:i + size], self.phase) for i in range(0, len(policies), size)]
        batches = map(evaluate_batch, tasks) if self.pool is None else self.pool.map(evaluate_batch, tasks)
        return [row for batch in batches for row in batch]
