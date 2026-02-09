"""
Continuous learning loop: collect data, generate candidates, evaluate, update, persist best config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from src.trader.ml.config_space import config_to_backtest_cfg, get_default_config_space
from src.trader.ml.knowledge_base import StrategyKnowledgeBase
from src.trader.ml.strategy_optimizer import StrategyOptimizer


def save_config(config: Dict[str, Any], path: Path | str) -> None:
    """Save best configuration to JSON for deployment."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, default=str)


def load_config_from_path(path: Path | str) -> Dict[str, Any]:
    """Load configuration from a JSON file."""
    import json

    with open(path, encoding="utf-8") as f:
        return json.load(f)


class MarketDataCollector:
    """
    Fetches latest market data for the learning cycle.
    Delegates to existing parquet loader / ensure_data.
    """

    def __init__(
        self,
        symbol: str = "XAUUSD",
        timeframe: str = "15m",
        base_path: str | Path = "data/market_cache",
        period_days: int = 60,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.base_path = Path(base_path)
        self.period_days = period_days

    def fetch_latest_data(self) -> bool:
        """
        Ensure latest data is available (e.g. trigger ensure_data).
        Returns True if data is present.
        """
        from src.trader.io.parquet_loader import ensure_data, load_parquet
        from datetime import datetime, timedelta

        end = datetime.now()
        start = end - timedelta(days=self.period_days)
        ensure_data(
            symbol=self.symbol,
            timeframe=self.timeframe,
            base_path=self.base_path,
            period_days=self.period_days,
        )
        df = load_parquet(self.base_path, self.symbol, self.timeframe, start=start, end=end)
        return not df.empty and len(df) >= 50


class ContinuousLearningAgent:
    """
    Orchestrates the continuous learning loop:
    collect data -> generate candidate configs -> evaluate -> update strategy -> save best.
    """

    def __init__(
        self,
        base_config: Dict[str, Any] | None = None,
        config_space: Dict[str, Any] | None = None,
        data_collector: MarketDataCollector | None = None,
        strategy_optimizer: StrategyOptimizer | None = None,
        knowledge_base: StrategyKnowledgeBase | None = None,
        best_config_path: str | Path = "reports/latest/best_ml_config.json",
        candidates_per_cycle: int = 5,
    ):
        self.base_config = base_config or {}
        self.config_space = config_space or get_default_config_space()
        self.data_collector = data_collector or MarketDataCollector()
        self.strategy_optimizer = strategy_optimizer or StrategyOptimizer(
            config_space=self.config_space,
            base_config=self._full_base_config(),
        )
        self.knowledge_base = knowledge_base or StrategyKnowledgeBase()
        self.best_config_path = Path(best_config_path)
        self.candidates_per_cycle = candidates_per_cycle

    def _full_base_config(self) -> Dict[str, Any]:
        """Base config including symbol, data, backtest defaults."""
        from src.trader.config import load_config

        cfg = load_config()
        cfg.update(self.base_config)
        return cfg

    def run_learning_cycle(self) -> Dict[str, Any]:
        """
        One learning cycle:
        1. Collect latest market data
        2. Generate and evaluate candidate configs
        3. Update strategy optimizer and knowledge base
        4. Save best configuration

        Returns summary: best_reward, n_evaluated, best_config_path.
        """
        self.strategy_optimizer.base_config = self._full_base_config()

        # Collect latest data
        ok = self.data_collector.fetch_latest_data()
        if not ok:
            return {"error": "no_data", "best_reward": None, "n_evaluated": 0}

        # Generate and test candidates
        rewards: List[float] = []
        for _ in range(self.candidates_per_cycle):
            config = self.strategy_optimizer.generate_candidate_config()
            reward = self.strategy_optimizer.evaluate_config(config)
            self.strategy_optimizer.update_strategy(config, reward)
            last = self.strategy_optimizer.historical_performance[-1]
            self.knowledge_base.record_evaluation(
                config=config,
                reward=reward,
                metrics=last["metrics"],
            )
            rewards.append(reward)

        # Persist best config
        best = self.strategy_optimizer.get_best_config()
        if best:
            save_config(config_to_backtest_cfg(best, self._full_base_config()), self.best_config_path)

        return {
            "best_reward": self.strategy_optimizer.best_reward,
            "n_evaluated": len(rewards),
            "rewards": rewards,
            "best_config_path": str(self.best_config_path),
        }
