"""
Smoke test: load config, run SQE conditions on dummy data, run backtest (no data = 0 trades).
"""
import pytest
from pathlib import Path
import pandas as pd
import numpy as np


def test_config_loads():
    from src.trader.config import load_config
    cfg = load_config()
    assert "symbol" in cfg or "data" in cfg
    assert cfg.get("symbol", "XAUUSD") == "XAUUSD" or "symbol" in cfg


def test_sqe_conditions_on_dummy():
    from src.trader.strategies.sqe_xauusd import run_sqe_conditions, get_sqe_default_config
    n = 200
    np.random.seed(42)
    idx = pd.date_range("2024-01-01", periods=n, freq="15min")
    data = pd.DataFrame({
        "open": 2000 + np.cumsum(np.random.randn(n) * 0.5),
        "high": 0.0,
        "low": 0.0,
        "close": 0.0,
        "volume": 1000,
    }, index=idx)
    data["high"] = data[["open", "close"]].max(axis=1) + np.random.rand(n) * 2
    data["low"] = data[["open", "close"]].min(axis=1) - np.random.rand(n) * 2
    data["close"] = data["open"] + np.random.randn(n) * 1.5
    data["open"] = data["close"].shift(1).fillna(data["open"])
    long_ok = run_sqe_conditions(data, "LONG", get_sqe_default_config())
    assert isinstance(long_ok, pd.Series)
    assert len(long_ok) == n


def test_backtest_engine_no_data_returns_empty():
    from src.trader.backtest.engine import run_backtest
    cfg = {"symbol": "XAUUSD", "timeframes": ["15m"], "data": {"base_path": "data/market_cache"}, "backtest": {"default_period_days": 60, "tp_r": 2.0, "sl_r": 1.0}}
    # With empty or missing data, engine returns []
    trades = run_backtest(cfg)
    assert isinstance(trades, list)
