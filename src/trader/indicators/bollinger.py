"""
Bollinger Bands – volatility and range detection.
"""
import pandas as pd


def bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> pd.DataFrame:
    """
    Compute Bollinger Bands.
    Returns DataFrame with columns: bb_upper, bb_middle, bb_lower, bb_width, bb_pct_b.
    """
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()

    upper = sma + std_dev * std
    lower = sma - std_dev * std
    width = (upper - lower) / sma  # Normalized width
    pct_b = (close - lower) / (upper - lower)  # %B: 0 = at lower, 1 = at upper

    return pd.DataFrame({
        "bb_upper": upper,
        "bb_middle": sma,
        "bb_lower": lower,
        "bb_width": width,
        "bb_pct_b": pct_b,
    }, index=close.index)


def bb_width(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.Series:
    """Compute just the Bollinger Band width (normalized)."""
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return (upper - lower) / sma


def bb_squeeze(close: pd.Series, period: int = 20, squeeze_pct: float = 25.0) -> pd.Series:
    """
    Detect Bollinger Band squeeze (narrow bands = low volatility).
    Returns True when BB width is in bottom `squeeze_pct`% of its range.
    """
    width = bb_width(close, period)
    percentile = width.rolling(50, min_periods=10).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )
    return percentile < (squeeze_pct / 100.0)
