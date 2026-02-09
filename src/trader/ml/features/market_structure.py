"""
Market structure features: swing structure, break of structure, trend context.
"""
from typing import Any, Dict

import numpy as np
import pandas as pd

from src.trader.indicators.swings import swing_highs, swing_lows


def add_market_structure_features(
    df: pd.DataFrame,
    config: Dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Add market structure features:
    - feat_swing_high / feat_swing_low (last swing levels)
    - feat_hh_hl: higher high / higher low sequence (1) or not (0)
    - feat_bos_bull / feat_bos_bear: break of structure (swing broken)
    - feat_trend_strength: simple trend strength from swing sequence
    """
    cfg = config or {}
    lookback = cfg.get("swing_lookback", 5)
    out = df.copy()

    sh = swing_highs(out["high"], lookback=lookback)
    sl = swing_lows(out["low"], lookback=lookback)
    out["feat_swing_high"] = sh
    out["feat_swing_low"] = sl

    # Forward-fill last known swing levels
    out["feat_last_swing_high"] = sh.ffill()
    out["feat_last_swing_low"] = sl.ffill()

    # Break of structure: price breaks last swing high (bull) or low (bear)
    out["feat_bos_bull"] = (out["high"] > out["feat_last_swing_high"].shift(1)).fillna(False)
    out["feat_bos_bear"] = (out["low"] < out["feat_last_swing_low"].shift(1)).fillna(False)

    # Simple trend: count of recent higher highs (1) vs lower highs (-1) over small window
    roll_high = out["high"].rolling(5, min_periods=1).max()
    out["feat_hh"] = (out["high"] >= roll_high).astype(np.float64)
    roll_low = out["low"].rolling(5, min_periods=1).min()
    out["feat_hl"] = (out["low"] <= roll_low).astype(np.float64)
    out["feat_trend_strength"] = (out["feat_hh"].rolling(10).mean() - out["feat_hl"].rolling(10).mean()).fillna(0)

    return out
