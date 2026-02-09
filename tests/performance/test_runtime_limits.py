"""Performance tests: runtime and resource guardrails (VPS stability)."""
import time
import pytest


def test_backtest_completes_within_reasonable_time():
    """Backtest should finish within 60s when data is small or missing."""
    from src.trader.config import load_config
    from src.trader.backtest.engine import run_backtest
    cfg = load_config()
    start = time.perf_counter()
    trades = run_backtest(cfg)
    elapsed = time.perf_counter() - start
    assert elapsed < 60.0, f"Backtest took {elapsed:.1f}s (max 60s)"
