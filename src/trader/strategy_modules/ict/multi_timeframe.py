"""
Multi-Timeframe Analysis — H4 context, daily bias, weekly key levels.

Provides higher-timeframe context for trade direction and key levels:
  - H4 structure (bullish/bearish) as directional bias
  - Daily bias from daily candle direction + structure
  - Weekly key levels (high/low of previous week as S/R)
"""
import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.trader.indicators.ema import ema
from src.trader.strategy_modules.ict.structure_context import add_structure_context

logger = logging.getLogger(__name__)


def compute_daily_bias(
    df_daily: pd.DataFrame,
    lookback: int = 5,
) -> pd.Series:
    """
    Compute daily bias: BULLISH, BEARISH, or NEUTRAL.
    Based on:
      - Last N daily candles direction
      - EMA alignment (10/20 on daily)
    """
    if df_daily.empty or len(df_daily) < lookback:
        return pd.Series("NEUTRAL", index=df_daily.index)

    # Daily candle direction
    daily_dir = (df_daily["close"] > df_daily["open"]).astype(int) - (df_daily["close"] < df_daily["open"]).astype(int)
    rolling_dir = daily_dir.rolling(lookback).sum()

    # EMA alignment
    ema10 = ema(df_daily["close"], 10)
    ema20 = ema(df_daily["close"], 20)

    bias = pd.Series("NEUTRAL", index=df_daily.index)
    bias[(rolling_dir > 2) & (ema10 > ema20)] = "BULLISH"
    bias[(rolling_dir < -2) & (ema10 < ema20)] = "BEARISH"

    return bias


def compute_weekly_levels(
    df_weekly: pd.DataFrame,
) -> Dict[str, float]:
    """
    Compute weekly key levels from previous week.
    Returns dict with: prev_week_high, prev_week_low, prev_week_open, prev_week_close.
    """
    if df_weekly.empty or len(df_weekly) < 2:
        return {}

    prev_week = df_weekly.iloc[-2]
    return {
        "prev_week_high": float(prev_week["high"]),
        "prev_week_low": float(prev_week["low"]),
        "prev_week_open": float(prev_week["open"]),
        "prev_week_close": float(prev_week["close"]),
    }


def compute_h4_structure(
    df_h4: pd.DataFrame,
    config: Optional[Dict] = None,
) -> pd.Series:
    """
    Compute H4 structure labels for directional bias.
    Returns: Series with 'BULLISH_STRUCTURE', 'BEARISH_STRUCTURE', or 'RANGE'.
    """
    if df_h4.empty or len(df_h4) < 30:
        return pd.Series("RANGE", index=df_h4.index)

    cfg = config or {"lookback": 20, "pivot_bars": 2}
    df = add_structure_context(df_h4.copy(), cfg)
    return df["structure_label"]


def get_htf_bias(
    df_15m: pd.DataFrame,
    df_1h: Optional[pd.DataFrame] = None,
    df_4h: Optional[pd.DataFrame] = None,
    df_daily: Optional[pd.DataFrame] = None,
) -> Dict[str, str]:
    """
    Get multi-timeframe bias from all available timeframes.
    Returns: {"h1": "BULLISH", "h4": "BEARISH", "daily": "BULLISH", "consensus": "MIXED"}
    """
    biases = {}

    # H1 structure
    if df_1h is not None and not df_1h.empty and len(df_1h) >= 30:
        h1_struct = add_structure_context(df_1h.copy(), {"lookback": 30, "pivot_bars": 2})
        last_struct = h1_struct["structure_label"].iloc[-1]
        biases["h1"] = "BULLISH" if "BULLISH" in str(last_struct) else "BEARISH" if "BEARISH" in str(last_struct) else "NEUTRAL"

    # H4 structure
    if df_4h is not None and not df_4h.empty and len(df_4h) >= 20:
        h4_struct = compute_h4_structure(df_4h)
        last_struct = h4_struct.iloc[-1]
        biases["h4"] = "BULLISH" if "BULLISH" in str(last_struct) else "BEARISH" if "BEARISH" in str(last_struct) else "NEUTRAL"

    # Daily bias
    if df_daily is not None and not df_daily.empty and len(df_daily) >= 5:
        daily_bias = compute_daily_bias(df_daily)
        biases["daily"] = daily_bias.iloc[-1]

    # Consensus
    if biases:
        bullish_count = sum(1 for v in biases.values() if v == "BULLISH")
        bearish_count = sum(1 for v in biases.values() if v == "BEARISH")
        total = len(biases)
        if bullish_count > total / 2:
            biases["consensus"] = "BULLISH"
        elif bearish_count > total / 2:
            biases["consensus"] = "BEARISH"
        else:
            biases["consensus"] = "MIXED"
    else:
        biases["consensus"] = "NEUTRAL"

    return biases
