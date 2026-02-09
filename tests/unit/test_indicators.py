"""Unit tests: indicator calculations, signal generation, risk sizing."""
import pandas as pd
import numpy as np
import pytest


def test_atr_output_shape():
    from src.trader.indicators.atr import atr
    n = 50
    high = pd.Series(2000 + np.random.rand(n) * 10)
    low = pd.Series(2000 - np.random.rand(n) * 10)
    close = pd.Series(2000 + np.random.randn(n) * 2)
    result = atr(high, low, close, period=14)
    assert len(result) == n
    assert result.iloc[-1] >= 0


def test_ema_output():
    from src.trader.indicators.ema import ema
    s = pd.Series([100, 102, 101, 105, 104])
    out = ema(s, 3)
    assert len(out) == len(s)
    assert out.iloc[-1] is not np.nan


def test_calculate_rr_long_win():
    from src.trader.data.schema import calculate_rr
    # entry 100, sl 98, exit 104 -> risk 2, profit 4 -> R = 2
    r = calculate_rr(100.0, 104.0, 98.0, "LONG")
    assert abs(r - 2.0) < 1e-6


def test_risk_check_max_daily_loss():
    from src.trader.execution.risk import check_max_daily_loss_r
    assert check_max_daily_loss_r(-2.0, 3.0) is True
    assert check_max_daily_loss_r(-4.0, 3.0) is False


def test_sizing_from_r():
    from src.trader.execution.sizing import size_from_r
    frac = size_from_r(10000.0, risk_r=1.0, risk_pct_per_r=0.01)
    assert frac == 0.01
