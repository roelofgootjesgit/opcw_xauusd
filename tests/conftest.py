"""Shared pytest fixtures and config."""
import pytest


@pytest.fixture
def sample_config():
    return {
        "symbol": "XAUUSD",
        "timeframes": ["15m"],
        "data": {"base_path": "data/market_cache"},
        "backtest": {"default_period_days": 60, "tp_r": 2.0, "sl_r": 1.0},
    }
