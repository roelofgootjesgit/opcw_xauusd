"""
Swing high/low detection (lookback bars each side).
"""
import pandas as pd
import numpy as np


def swing_highs(high: pd.Series, lookback: int = 5) -> pd.Series:
    out = pd.Series(np.nan, index=high.index)
    for i in range(lookback, len(high) - lookback):
        window = high.iloc[i - lookback : i + lookback + 1]
        if high.iloc[i] == window.max():
            out.iloc[i] = high.iloc[i]
    return out


def swing_lows(low: pd.Series, lookback: int = 5) -> pd.Series:
    out = pd.Series(np.nan, index=low.index)
    for i in range(lookback, len(low) - lookback):
        window = low.iloc[i - lookback : i + lookback + 1]
        if low.iloc[i] == window.min():
            out.iloc[i] = low.iloc[i]
    return out
