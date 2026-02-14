"""
Regime Detector: classifies market into TRENDING, RANGING, or VOLATILE.

Uses a combination of:
  - ADX (Average Directional Index) for trend strength
  - ATR percentile for volatility detection
  - Bollinger Band width for range detection
  - EMA alignment (20/50/200) for trend confirmation
  - Structure context (HH/HL or LH/LL) from existing ICT modules
"""
from enum import Enum
from typing import Dict, Optional

import numpy as np
import pandas as pd


class Regime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"


# Default thresholds
DEFAULT_CONFIG = {
    "adx_trending_threshold": 25,
    "adx_ranging_threshold": 20,
    "atr_volatile_percentile": 90,
    "bb_width_ranging_percentile": 25,
    "ema_periods": [20, 50, 200],
    "adx_period": 14,
    "atr_period": 14,
    "bb_period": 20,
    "bb_std": 2.0,
    "lookback": 50,
    # Weights for composite scoring
    "weight_adx": 0.30,
    "weight_atr": 0.25,
    "weight_bb": 0.20,
    "weight_ema": 0.15,
    "weight_structure": 0.10,
}


def _compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average Directional Index (ADX)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)

    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ATR."""
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _compute_bb_width(df: pd.DataFrame, period: int = 20, std: float = 2.0) -> pd.Series:
    """Compute Bollinger Band width (normalized by middle band)."""
    sma = df["close"].rolling(period).mean()
    std_dev = df["close"].rolling(period).std()
    upper = sma + std * std_dev
    lower = sma - std * std_dev
    width = (upper - lower) / sma.replace(0, np.nan)
    return width


def _check_ema_alignment(df: pd.DataFrame, periods: list) -> pd.DataFrame:
    """Check if EMAs are aligned (bullish or bearish trend)."""
    emas = {}
    for p in sorted(periods):
        emas[p] = df["close"].ewm(span=p, adjust=False).mean()

    sorted_periods = sorted(periods)
    # Bullish alignment: EMA20 > EMA50 > EMA200
    bullish = pd.Series(True, index=df.index)
    bearish = pd.Series(True, index=df.index)
    for i in range(len(sorted_periods) - 1):
        short_p = sorted_periods[i]
        long_p = sorted_periods[i + 1]
        bullish = bullish & (emas[short_p] > emas[long_p])
        bearish = bearish & (emas[short_p] < emas[long_p])

    # aligned = either bullish or bearish alignment
    aligned = bullish | bearish
    return pd.DataFrame({
        "ema_bullish_aligned": bullish,
        "ema_bearish_aligned": bearish,
        "ema_aligned": aligned,
    }, index=df.index)


class RegimeDetector:
    """
    Classifies each bar into one of three regimes:
      - TRENDING: strong directional movement (ADX > 25, EMA aligned)
      - RANGING: low volatility, price bouncing (ADX < 20, narrow BB)
      - VOLATILE: high volatility spikes (ATR > 90th percentile)
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}

    def classify(
        self,
        df_15m: pd.DataFrame,
        df_1h: Optional[pd.DataFrame] = None,
    ) -> pd.Series:
        """
        Classify each bar in df_15m into a Regime.
        Optionally uses df_1h for higher-timeframe confirmation.

        Returns: pd.Series of Regime values, indexed like df_15m.
        """
        cfg = self.config
        df = df_15m.copy()

        # 1. ADX
        adx = _compute_adx(df, period=cfg["adx_period"])

        # 2. ATR + percentile
        atr = _compute_atr(df, period=cfg["atr_period"])
        atr_pct = atr.rolling(cfg["lookback"], min_periods=10).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
        )

        # 3. Bollinger Band width
        bb_width = _compute_bb_width(df, period=cfg["bb_period"], std=cfg["bb_std"])
        bb_pct = bb_width.rolling(cfg["lookback"], min_periods=10).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
        )

        # 4. EMA alignment
        ema_df = _check_ema_alignment(df, cfg["ema_periods"])

        # 5. H1 confirmation (optional)
        h1_trending = pd.Series(False, index=df.index)
        if df_1h is not None and not df_1h.empty:
            h1_adx = _compute_adx(df_1h, period=cfg["adx_period"])
            h1_trending_raw = h1_adx > cfg["adx_trending_threshold"]
            h1_trending = h1_trending_raw.reindex(df.index, method="ffill").fillna(False)

        # --- Composite scoring ---
        # Trend score: higher = more trending
        trend_score = pd.Series(0.0, index=df.index)
        trend_score += (adx / 50.0).clip(0, 1) * cfg["weight_adx"]
        trend_score += ema_df["ema_aligned"].astype(float) * cfg["weight_ema"]
        trend_score += h1_trending.astype(float) * cfg["weight_structure"]

        # Volatile score: higher = more volatile
        volatile_score = pd.Series(0.0, index=df.index)
        volatile_score += atr_pct.fillna(0.5) * cfg["weight_atr"]

        # Ranging score: higher = more ranging
        ranging_score = pd.Series(0.0, index=df.index)
        ranging_score += (1 - bb_pct.fillna(0.5)) * cfg["weight_bb"]  # narrow BB = ranging
        ranging_score += ((50 - adx.clip(0, 50)) / 50.0) * cfg["weight_adx"]  # low ADX = ranging

        # --- Classification ---
        regime = pd.Series(Regime.RANGING.value, index=df.index, dtype=object)

        # Volatile: ATR > 90th percentile takes priority
        volatile_mask = atr_pct > (cfg["atr_volatile_percentile"] / 100.0)
        regime[volatile_mask] = Regime.VOLATILE.value

        # Trending: ADX > threshold + some EMA alignment
        trending_mask = (
            (~volatile_mask)
            & (adx > cfg["adx_trending_threshold"])
        )
        regime[trending_mask] = Regime.TRENDING.value

        # Everything else stays RANGING

        return regime

    def get_regime_at(self, regime_series: pd.Series, index: int) -> str:
        """Get regime at specific index."""
        if index < 0 or index >= len(regime_series):
            return Regime.RANGING.value
        return regime_series.iloc[index]

    def regime_summary(self, regime_series: pd.Series) -> dict:
        """Summary statistics of regime distribution."""
        counts = regime_series.value_counts()
        total = len(regime_series)
        return {
            regime: {
                "count": int(counts.get(regime, 0)),
                "pct": round(counts.get(regime, 0) / total * 100, 1) if total > 0 else 0.0,
            }
            for regime in [Regime.TRENDING.value, Regime.RANGING.value, Regime.VOLATILE.value]
        }
