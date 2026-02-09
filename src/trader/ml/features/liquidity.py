"""
Liquidity-related features: sweep proximity, liquidity zones, volume context.
"""
from typing import Any, Dict

import numpy as np
import pandas as pd


def add_liquidity_features(
    df: pd.DataFrame,
    config: Dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Add liquidity indicators:
    - feat_dist_to_swing_high/low: distance to nearest swing (normalized by ATR)
    - feat_sweep_zone: 1 if price is near a recent swing (liquidity zone)
    - feat_volume_ma_ratio: volume relative to moving average (if volume present)
    """
    cfg = config or {}
    lookback = cfg.get("lookback", 20)
    atr_period = cfg.get("atr_period", 14)
    out = df.copy()

    # ATR for normalization
    tr = np.maximum(
        out["high"] - out["low"],
        np.maximum(
            (out["high"] - out["close"].shift(1)).abs(),
            (out["low"] - out["close"].shift(1)).abs(),
        ),
    )
    atr = tr.ewm(alpha=1 / atr_period, adjust=False).mean()
    atr = atr.replace(0, np.nan).ffill().bfill()

    swing_high = out["high"].rolling(lookback, min_periods=1).max().shift(1)
    swing_low = out["low"].rolling(lookback, min_periods=1).min().shift(1)

    out["feat_dist_to_swing_high"] = ((swing_high - out["high"]) / atr).fillna(0)
    out["feat_dist_to_swing_low"] = ((out["low"] - swing_low) / atr).fillna(0)

    # Within N ATR of swing = liquidity zone
    thresh = cfg.get("sweep_threshold_atr", 0.5)
    out["feat_sweep_zone_high"] = (out["feat_dist_to_swing_high"].abs() <= thresh).astype(np.float64)
    out["feat_sweep_zone_low"] = (out["feat_dist_to_swing_low"].abs() <= thresh).astype(np.float64)

    if "volume" in out.columns and out["volume"].gt(0).any():
        vol_ma = out["volume"].rolling(20, min_periods=1).mean()
        out["feat_volume_ma_ratio"] = (out["volume"] / vol_ma.replace(0, np.nan)).fillna(1.0)
    else:
        out["feat_volume_ma_ratio"] = 1.0

    return out
