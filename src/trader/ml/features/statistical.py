"""
Statistical measures: rolling volatility, return distribution, z-scores.
"""
from typing import Any, Dict

import numpy as np
import pandas as pd


def add_statistical_features(
    df: pd.DataFrame,
    config: Dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Add statistical features:
    - feat_returns: log return
    - feat_volatility: rolling std of returns
    - feat_zscore: z-score of close relative to rolling mean/std
    - feat_skew_like: rolling skewness of returns (simplified)
    """
    cfg = config or {}
    roll = cfg.get("rolling", 20)
    out = df.copy()

    out["feat_returns"] = np.log(out["close"] / out["close"].shift(1)).fillna(0)
    out["feat_volatility"] = out["feat_returns"].rolling(roll, min_periods=2).std().fillna(0)
    roll_mean = out["close"].rolling(roll, min_periods=2).mean()
    roll_std = out["close"].rolling(roll, min_periods=2).std().replace(0, np.nan)
    out["feat_zscore"] = ((out["close"] - roll_mean) / roll_std).fillna(0)

    # Simplified skew: (mean - median) / std over rolling window
    roll_median = out["close"].rolling(roll, min_periods=2).median()
    out["feat_skew_like"] = ((roll_mean - roll_median) / roll_std.replace(0, np.nan)).fillna(0)

    return out
