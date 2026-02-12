"""Integration tests: config load -> data -> backtest path, execution stub."""
import pytest


def test_config_load_and_backtest_engine_import():
    from src.trader.config import load_config
    from src.trader.backtest.engine import run_backtest
    cfg = load_config()
    assert "symbol" in cfg or "data" in cfg
    # Korte periode zodat test niet hangt op trage VPS
    cfg.setdefault("backtest", {})["default_period_days"] = 7
    trades = run_backtest(cfg)
    assert isinstance(trades, list)


def test_broker_stub_accepts_order():
    from src.trader.execution.broker_stub import submit_order, OrderRequest
    req = OrderRequest(symbol="XAUUSD", direction="BUY", volume=0.01, sl=2000.0, tp=2010.0)
    assert submit_order(req) is True
