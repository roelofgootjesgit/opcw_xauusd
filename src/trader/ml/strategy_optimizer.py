"""
Strategy optimizer: Multi-Armed Bandit / Thompson Sampling style optimization.
Generates candidate configs, evaluates via backtest, updates belief over config space.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from src.trader.backtest.engine import run_backtest
from src.trader.backtest.metrics import compute_metrics
from src.trader.ml.config_space import (
    config_to_backtest_cfg,
    get_default_config_space,
    sample_config,
)
from src.trader.ml.rewards import calculate_reward


def _default_backtest_fn(cfg: Dict[str, Any]) -> list:
    """Run backtest and return list of trades."""
    return run_backtest(cfg)


class StrategyOptimizer:
    """
    Uses intelligent sampling (Thompson Sampling style) over a probabilistic
    config space: generate candidates, evaluate, update strategy.
    """

    def __init__(
        self,
        config_space: Dict[str, Any] | None = None,
        base_config: Dict[str, Any] | None = None,
        backtest_fn: Callable[[Dict[str, Any]], list] | None = None,
        reward_weights: Dict[str, float] | None = None,
        seed: int | None = None,
    ):
        self.config_space = config_space or get_default_config_space()
        self.base_config = base_config or {}
        self.backtest_fn = backtest_fn or _default_backtest_fn
        self.reward_weights = reward_weights
        self.historical_performance: List[Dict[str, Any]] = []
        self.best_config: Dict[str, Any] | None = None
        self.best_reward: float = -np.inf
        self._rng = np.random.default_rng(seed)
        # Thompson Sampling: maintain running mean reward per "arm" (we use continuous arms;
        # we approximate by keeping best-so-far and biasing toward it)
        self._best_sampled: Dict[str, Any] | None = None

    def generate_candidate_config(self) -> Dict[str, Any]:
        """
        Generate a new configuration variation.
        With probability epsilon, sample uniformly; else bias toward best-so-far (exploitation).
        """
        if self._best_sampled is not None and self._rng.uniform(0, 1) < 0.3:
            # Exploit: perturb around best
            candidate = self._perturb_config(self._best_sampled)
        else:
            candidate = sample_config(self.config_space, base_config=None, rng=self._rng)
        return candidate

    def _perturb_config(self, config: Dict[str, Any], scale: float = 0.2) -> Dict[str, Any]:
        """Perturb numeric values in config for local search."""
        out = copy.deepcopy(config)
        strategy = out.get("strategy", {})
        for module_name, params in list(strategy.items()):
            if module_name == "use_mss" or not isinstance(params, dict):
                continue
            for key, val in params.items():
                if isinstance(val, (int, float)):
                    delta = self._rng.uniform(-scale * abs(val) - 0.1, scale * abs(val) + 0.1)
                    new_val = val + delta
                    if key in (
                        "lookback_candles",
                        "reversal_candles",
                        "min_candles",
                        "validity_candles",
                        "swing_lookback",
                    ):
                        new_val = int(np.clip(round(new_val), 1, 500))
                    strategy[module_name][key] = new_val
        backtest = out.get("backtest", {})
        for key in ("tp_r", "sl_r"):
            if key in backtest and isinstance(backtest[key], (int, float)):
                backtest[key] = float(
                    np.clip(
                        backtest[key] + self._rng.uniform(-0.2, 0.2),
                        0.5,
                        5.0,
                    )
                )
        return out

    def evaluate_config(self, config: Dict[str, Any]) -> float:
        """
        Run backtest with config, compute metrics, return reward.
        """
        full_cfg = config_to_backtest_cfg(config, self.base_config)
        trades = self.backtest_fn(full_cfg)
        metrics = compute_metrics(trades)
        reward = calculate_reward(metrics, self.reward_weights)
        self.historical_performance.append(
            {"config": copy.deepcopy(config), "metrics": metrics, "reward": reward}
        )
        return reward

    def update_strategy(self, config: Dict[str, Any], reward: float) -> None:
        """
        Update strategy based on performance (Thompson Sampling style:
        keep best config for exploitation).
        """
        if reward > self.best_reward:
            self.best_reward = reward
            self.best_config = copy.deepcopy(config)
            self._best_sampled = copy.deepcopy(config)

    def get_best_config(self) -> Dict[str, Any] | None:
        """Return best configuration found so far."""
        return copy.deepcopy(self.best_config) if self.best_config else None

    def run_optimization_step(self) -> float:
        """
        Generate one candidate, evaluate, update. Returns reward of this step.
        """
        config = self.generate_candidate_config()
        reward = self.evaluate_config(config)
        self.update_strategy(config, reward)
        return reward

    def run_n_steps(self, n: int) -> List[float]:
        """Run n optimization steps; return list of rewards."""
        rewards: List[float] = []
        for _ in range(n):
            r = self.run_optimization_step()
            rewards.append(r)
        return rewards
