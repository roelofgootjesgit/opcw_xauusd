"""
Technical indicators as features: ATR, EMA, momentum, RSI-like.
"""
from typing import Any, Dict

import numpy as np
import pandas as pd

from src.trader.indicators.atr import atr
from src.trader.indicators.ema import ema


def add_technical_features(
    df: pd.DataFrame,
    config: Dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Add technical features:
    - feat_atr_pct: ATR as % of close (volatility)
    - feat_ema_fast, feat_ema_slow: EMAs
    - feat_price_above_ema: 1 if close > EMA
    - feat_momentum: short-term return (e.g. 5-bar)
    - feat_rsi_like: RSI-like oscillator [0,1] from gains/losses
    """
    cfg = config or {}
    atr_period = cfg.get("atr_period", 14)
    ema_fast = cfg.get("ema_fast", 9)
    ema_slow = cfg.get("ema_slow", 21)
    momentum_bars = cfg.get("momentum_bars", 5)
    rsi_period = cfg.get("rsi_period", 14)
    out = df.copy()

    atr_series = atr(out["high"], out["low"], out["close"], period=atr_period)
    out["feat_atr_pct"] = (atr_series / out["close"]).fillna(0)
    out["feat_atr"] = atr_series

    out["feat_ema_fast"] = ema(out["close"], ema_fast)
    out["feat_ema_slow"] = ema(out["close"], ema_slow)
    out["feat_price_above_ema"] = (out["close"] > out["feat_ema_fast"]).astype(np.float64)

    out["feat_momentum"] = (out["close"] / out["close"].shift(momentum_bars) - 1.0).fillna(0)

    delta = out["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / rsi_period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out["feat_rsi_like"] = (1 - 1 / (1 + rs)).fillna(0.5)

    return out
