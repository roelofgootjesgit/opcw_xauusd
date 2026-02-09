"""Unit tests for ML framework: config space, rewards, features, optimizer."""
import numpy as np
import pandas as pd
import pytest

from src.trader.ml.config_space import get_default_config_space, sample_config, config_to_backtest_cfg
from src.trader.ml.rewards import calculate_reward, calculate_reward_from_trades
from src.trader.ml.features.pipeline import FeatureExtractionPipeline
from src.trader.ml.strategy_optimizer import StrategyOptimizer
from src.trader.data.schema import Trade
from datetime import datetime, timedelta


@pytest.fixture
def config_space():
    return get_default_config_space()


@pytest.fixture
def sample_metrics():
    return {
        "total_profit_r": 2.0,
        "profit_factor": 1.5,
        "max_drawdown": -0.5,
        "win_rate_01": 0.6,
    }


def test_sample_config(config_space):
    rng = np.random.default_rng(42)
    c = sample_config(config_space, rng=rng)
    assert "backtest" in c
    assert "strategy" in c
    assert 1.5 <= c["backtest"]["tp_r"] <= 3.0
    assert 0.5 <= c["backtest"]["sl_r"] <= 2.0
    assert isinstance(c["strategy"]["liquidity_sweep"]["lookback_candles"], (int, np.integer))
    assert c["strategy"]["use_mss"] in (True, False)


def test_config_to_backtest_cfg(config_space):
    base = {"symbol": "XAUUSD", "timeframes": ["15m"], "data": {"base_path": "data/market_cache"}}
    sampled = sample_config(config_space, rng=np.random.default_rng(1))
    merged = config_to_backtest_cfg(sampled, base)
    assert merged["symbol"] == "XAUUSD"
    assert "tp_r" in merged["backtest"]
    assert "liquidity_sweep" in merged["strategy"]


def test_calculate_reward(sample_metrics):
    r = calculate_reward(sample_metrics)
    assert isinstance(r, (float, np.floating))
    assert r > 0
    r2 = calculate_reward({}, weights={"net_pnl": 1.0, "profit_factor": 0, "max_drawdown": 0, "win_rate": 0})
    assert r2 == 0.0


def test_calculate_reward_from_trades():
    trades = [
        Trade(
            timestamp_open=datetime.now(),
            timestamp_close=datetime.now() + timedelta(hours=1),
            symbol="XAUUSD",
            direction="LONG",
            entry_price=2000.0,
            exit_price=2010.0,
            sl=1990.0,
            tp=2020.0,
            profit_usd=10.0,
            profit_r=0.5,
            result="WIN",
        ),
    ]
    r = calculate_reward_from_trades(trades)
    assert isinstance(r, (float, np.floating))


def test_feature_pipeline():
    n = 100
    idx = pd.date_range("2024-01-01", periods=n, freq="15min")
    df = pd.DataFrame(
        {
            "open": 2000 + np.cumsum(np.random.randn(n) * 2),
            "high": 2000 + np.cumsum(np.random.randn(n) * 2) + np.abs(np.random.randn(n)) * 5,
            "low": 2000 + np.cumsum(np.random.randn(n) * 2) - np.abs(np.random.randn(n)) * 5,
            "close": 2000 + np.cumsum(np.random.randn(n) * 2),
            "volume": np.random.randint(1000, 10000, n),
        },
        index=idx,
    )
    pipeline = FeatureExtractionPipeline()
    out = pipeline.fit_transform(df)
    assert "feat_atr_pct" in out.columns
    assert "feat_swing_high" in out.columns
    assert "feat_returns" in out.columns
    assert len(pipeline.feature_columns) >= 10


def test_strategy_optimizer_generate_and_evaluate(sample_config):
    """Test that optimizer generates configs and can evaluate via mock backtest."""
    base = {**sample_config, "backtest": {**sample_config.get("backtest", {}), "default_period_days": 30}}

    def mock_backtest(_cfg):
        # Return empty trades so we don't need data or timezone handling
        return []

    opt = StrategyOptimizer(base_config=base, backtest_fn=mock_backtest, seed=123)
    c = opt.generate_candidate_config()
    assert "backtest" in c and "strategy" in c
    reward = opt.evaluate_config(c)
    assert isinstance(reward, (float, np.floating))
    opt.update_strategy(c, reward)
    assert opt.historical_performance
    assert opt.get_best_config() is not None
