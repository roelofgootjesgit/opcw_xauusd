"""
ADX (Average Directional Index) – trend strength measurement.
"""
import numpy as np
import pandas as pd


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Compute the Average Directional Index (ADX).
    ADX > 25 = trending, ADX < 20 = ranging.
    """
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_val = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_val)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_val)

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx_val = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_val


def plus_di(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Compute +DI (positive directional indicator)."""
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_val = tr.ewm(alpha=1 / period, adjust=False).mean()
    return 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_val)


def minus_di(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Compute -DI (negative directional indicator)."""
    plus_dm = high.diff()
    minus_dm = -low.diff()
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_val = tr.ewm(alpha=1 / period, adjust=False).mean()
    return 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_val)
