"""
Machine learning framework for trading strategy optimization.

Components:
- features: Feature engineering pipeline (market structure, liquidity, technical, statistical)
- config_space: Probabilistic configuration space and sampling
- rewards: Multi-objective reward / fitness functions
- strategy_optimizer: StrategyOptimizer (Thompson Sampling, candidate generation)
- knowledge_base: Meta-learning (genealogy, regimes, successful configs)
- continuous_learning: ContinuousLearningAgent and learning loop
"""
from src.trader.ml.config_space import get_default_config_space, sample_config
from src.trader.ml.rewards import calculate_reward
from src.trader.ml.strategy_optimizer import StrategyOptimizer
from src.trader.ml.continuous_learning import (
    ContinuousLearningAgent,
    MarketDataCollector,
    save_config,
    load_config_from_path,
)

__all__ = [
    "StrategyOptimizer",
    "ContinuousLearningAgent",
    "MarketDataCollector",
    "calculate_reward",
    "get_default_config_space",
    "sample_config",
    "save_config",
    "load_config_from_path",
]
