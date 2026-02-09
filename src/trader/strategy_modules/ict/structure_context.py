"""
Expliciete marktstructuur: HH/HL (bullish), LH/LL (bearish), of RANGE.
Alleen trades toestaan in duidelijke structuur; RANGE blokkeren (OCLW_PRINCIPLES).
"""
from typing import Dict

import pandas as pd

from src.trader.strategy_modules.ict.structure_labels import (
    BULLISH_STRUCTURE,
    BEARISH_STRUCTURE,
    RANGE,
)


def compute_structure_labels(
    data: pd.DataFrame,
    lookback: int = 30,
    pivot_bars: int = 2,
) -> pd.Series:
    """
    Per bar: BULLISH_STRUCTURE (HH/HL), BEARISH_STRUCTURE (LH/LL), of RANGE.
    - HH/HL: laatste swing high > vorige, laatste swing low > vorige.
    - LH/LL: laatste swing high < vorige, laatste swing low < vorige.
    - Anders: RANGE.
    """
    df = data.copy()
    n = len(df)
    # Pivot highs/lows: lokaal max/min over (2 * pivot_bars + 1)
    high_roll = df["high"].rolling(2 * pivot_bars + 1, center=True, min_periods=pivot_bars + 1).max()
    low_roll = df["low"].rolling(2 * pivot_bars + 1, center=True, min_periods=pivot_bars + 1).min()
    is_pivot_high = (df["high"] == high_roll) & high_roll.notna()
    is_pivot_low = (df["low"] == low_roll) & low_roll.notna()

    out = pd.Series(index=df.index, dtype=object)
    out[:] = RANGE

    for i in range(lookback, n):
        start = max(0, i - lookback)
        # Pivot highs/lows in window: waar high resp. low lokaal max/min is
        window_high = df["high"].iloc[start : i + 1].values
        window_low = df["low"].iloc[start : i + 1].values
        is_ph = is_pivot_high.iloc[start : i + 1].values
        is_pl = is_pivot_low.iloc[start : i + 1].values

        ph_vals = window_high[is_ph]
        pl_vals = window_low[is_pl]
        if len(ph_vals) < 2 or len(pl_vals) < 2:
            continue

        sh2, sh1 = ph_vals[-1], ph_vals[-2]
        sl2, sl1 = pl_vals[-1], pl_vals[-2]

        if sh2 > sh1 and sl2 > sl1:
            out.iloc[i] = BULLISH_STRUCTURE
        elif sh2 < sh1 and sl2 < sl1:
            out.iloc[i] = BEARISH_STRUCTURE
        # else blijft RANGE

    return out


def add_structure_context(df: pd.DataFrame, config: Dict) -> pd.DataFrame:
    """Add structure_label column (BULLISH_STRUCTURE, BEARISH_STRUCTURE, RANGE)."""
    lookback = config.get("lookback", 30)
    pivot_bars = config.get("pivot_bars", 2)
    df = df.copy()
    df["structure_label"] = compute_structure_labels(df, lookback=lookback, pivot_bars=pivot_bars)
    df["in_bullish_structure"] = df["structure_label"] == BULLISH_STRUCTURE
    df["in_bearish_structure"] = df["structure_label"] == BEARISH_STRUCTURE
    return df
