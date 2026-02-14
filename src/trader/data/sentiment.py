"""
Sentiment Engine for XAUUSD.

Combines multiple data sources into a composite sentiment score
ranging from -1.0 (extremely bearish) to +1.0 (extremely bullish).

Sources:
  - DXY (Dollar Index) — inverse correlation with gold
  - US10Y Yields — inverse correlation (opportunity cost of holding gold)
  - VIX — fear/volatility gauge (positive for gold as safe haven)
  - COT Reports (CFTC) — institutional positioning in gold futures
  - Gold ETF flows (GLD) — institutional demand signal
  - CNN Fear & Greed Index — broad market sentiment
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SentimentReading:
    """A single sentiment data point."""
    source: str
    value: float  # raw value
    normalized: float  # -1.0 to +1.0 (bullish for gold)
    weight: float
    timestamp: Optional[datetime] = None
    stale: bool = False  # True if data is older than expected


@dataclass
class CompositeSentiment:
    """Composite sentiment score with breakdown."""
    score: float  # -1.0 to +1.0
    confidence: float  # 0.0 to 1.0 (based on data freshness)
    readings: List[SentimentReading]
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "confidence": round(self.confidence, 2),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "readings": {
                r.source: {
                    "value": round(r.value, 4),
                    "normalized": round(r.normalized, 3),
                    "weight": r.weight,
                    "stale": r.stale,
                }
                for r in self.readings
            },
        }


# Default weights
DEFAULT_WEIGHTS = {
    "dxy": 0.25,
    "cot": 0.25,
    "us10y": 0.15,
    "vix": 0.15,
    "etf_flows": 0.10,
    "fear_greed": 0.10,
}

# Default sentiment config
DEFAULT_SENTIMENT_CONFIG = {
    "enabled": False,
    "weights": DEFAULT_WEIGHTS,
    "min_score_long": 0.1,  # min sentiment for LONG entry
    "min_score_short": -0.1,  # max sentiment for SHORT entry (more negative = more bearish)
    "strong_signal_boost": 0.3,  # score threshold for position size boost
    "strong_signal_multiplier": 1.5,  # boost multiplier
    "contrary_block": True,  # block trades contrary to strong sentiment
    "contrary_threshold": 0.3,  # abs(score) threshold for contrary blocking
    "stale_data_hours": {
        "dxy": 4,
        "us10y": 4,
        "vix": 4,
        "cot": 168,  # weekly (7 days)
        "etf_flows": 24,
        "fear_greed": 24,
    },
}


def _normalize_inverse(value: float, mean: float, std: float) -> float:
    """
    Normalize a value inversely: higher value = more bearish for gold.
    Returns -1.0 to +1.0 where positive = bullish for gold.
    """
    if std <= 0:
        return 0.0
    z = (value - mean) / std
    return float(np.clip(-np.tanh(z), -1.0, 1.0))


def _normalize_direct(value: float, mean: float, std: float) -> float:
    """
    Normalize a value directly: higher value = more bullish for gold.
    Returns -1.0 to +1.0 where positive = bullish for gold.
    """
    if std <= 0:
        return 0.0
    z = (value - mean) / std
    return float(np.clip(np.tanh(z), -1.0, 1.0))


class SentimentEngine:
    """
    Multi-source sentiment engine for XAUUSD.
    Combines DXY, US10Y, VIX, COT, ETF flows, and Fear & Greed
    into a single composite score.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = {**DEFAULT_SENTIMENT_CONFIG, **(config or {})}
        self.weights = self.config.get("weights", DEFAULT_WEIGHTS)
        self._cache: Dict[str, Tuple[float, datetime]] = {}

    def compute_dxy_sentiment(
        self,
        dxy_series: pd.Series,
        lookback: int = 50,
    ) -> SentimentReading:
        """
        DXY (Dollar Index) — inverse correlation with gold.
        Strong dollar = bearish for gold, weak dollar = bullish.
        """
        if dxy_series is None or len(dxy_series) < 10:
            return SentimentReading("dxy", 0.0, 0.0, self.weights.get("dxy", 0.25), stale=True)

        recent = dxy_series.tail(lookback)
        current = float(dxy_series.iloc[-1])
        mean = float(recent.mean())
        std = float(recent.std())

        normalized = _normalize_inverse(current, mean, std)
        return SentimentReading("dxy", current, normalized, self.weights.get("dxy", 0.25))

    def compute_us10y_sentiment(
        self,
        yield_series: pd.Series,
        lookback: int = 50,
    ) -> SentimentReading:
        """
        US 10Y Yield — inverse correlation with gold.
        Higher yields = bearish (opportunity cost), lower yields = bullish.
        """
        if yield_series is None or len(yield_series) < 10:
            return SentimentReading("us10y", 0.0, 0.0, self.weights.get("us10y", 0.15), stale=True)

        recent = yield_series.tail(lookback)
        current = float(yield_series.iloc[-1])
        mean = float(recent.mean())
        std = float(recent.std())

        normalized = _normalize_inverse(current, mean, std)
        return SentimentReading("us10y", current, normalized, self.weights.get("us10y", 0.15))

    def compute_vix_sentiment(
        self,
        vix_series: pd.Series,
        lookback: int = 50,
    ) -> SentimentReading:
        """
        VIX (Fear Index) — positive correlation with gold as safe haven.
        Higher VIX = more fear = bullish for gold.
        """
        if vix_series is None or len(vix_series) < 10:
            return SentimentReading("vix", 0.0, 0.0, self.weights.get("vix", 0.15), stale=True)

        recent = vix_series.tail(lookback)
        current = float(vix_series.iloc[-1])
        mean = float(recent.mean())
        std = float(recent.std())

        normalized = _normalize_direct(current, mean, std)
        return SentimentReading("vix", current, normalized, self.weights.get("vix", 0.15))

    def compute_cot_sentiment(
        self,
        net_long_series: pd.Series,
        lookback: int = 26,  # ~6 months of weekly data
    ) -> SentimentReading:
        """
        COT (Commitment of Traders) — net long positions in gold futures.
        Higher net long = bullish institutional positioning.
        """
        if net_long_series is None or len(net_long_series) < 5:
            return SentimentReading("cot", 0.0, 0.0, self.weights.get("cot", 0.25), stale=True)

        recent = net_long_series.tail(lookback)
        current = float(net_long_series.iloc[-1])
        mean = float(recent.mean())
        std = float(recent.std())

        normalized = _normalize_direct(current, mean, std)
        return SentimentReading("cot", current, normalized, self.weights.get("cot", 0.25))

    def compute_etf_flow_sentiment(
        self,
        volume_series: pd.Series,
        price_series: pd.Series,
        lookback: int = 20,
    ) -> SentimentReading:
        """
        Gold ETF (GLD) flows — volume * price direction.
        High volume + rising price = bullish institutional demand.
        """
        if volume_series is None or price_series is None or len(volume_series) < 10:
            return SentimentReading("etf_flows", 0.0, 0.0, self.weights.get("etf_flows", 0.10), stale=True)

        # Dollar volume flow = volume * daily return direction
        returns = price_series.pct_change()
        flow = volume_series * returns.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
        recent = flow.tail(lookback)
        current = float(recent.sum())  # cumulative flow over lookback
        mean = float(recent.mean())
        std = float(recent.std())

        normalized = _normalize_direct(current, mean, std) if std > 0 else 0.0
        return SentimentReading("etf_flows", current, normalized, self.weights.get("etf_flows", 0.10))

    def compute_fear_greed_sentiment(
        self,
        fg_value: float,  # 0 = extreme fear, 100 = extreme greed
    ) -> SentimentReading:
        """
        CNN Fear & Greed Index.
        Extreme fear (low) = bullish for gold (safe haven demand).
        Extreme greed (high) = bearish for gold (risk-on).
        """
        # Normalize: 0 = extreme fear (+1.0 for gold), 100 = extreme greed (-1.0)
        normalized = float(np.clip(-(fg_value - 50) / 50.0, -1.0, 1.0))
        return SentimentReading("fear_greed", fg_value, normalized, self.weights.get("fear_greed", 0.10))

    def composite_score(self, readings: List[SentimentReading]) -> CompositeSentiment:
        """
        Calculate weighted composite sentiment score from all readings.
        """
        if not readings:
            return CompositeSentiment(score=0.0, confidence=0.0, readings=[])

        total_weight = 0.0
        weighted_sum = 0.0
        stale_count = 0

        for r in readings:
            if r.stale:
                stale_count += 1
                continue
            weighted_sum += r.normalized * r.weight
            total_weight += r.weight

        score = weighted_sum / total_weight if total_weight > 0 else 0.0
        confidence = 1.0 - (stale_count / len(readings)) if readings else 0.0

        return CompositeSentiment(
            score=float(np.clip(score, -1.0, 1.0)),
            confidence=confidence,
            readings=readings,
        )

    def should_allow_trade(
        self,
        sentiment: CompositeSentiment,
        direction: str,
    ) -> bool:
        """
        Check if a trade should be allowed based on sentiment.
        Returns True if trade is allowed.
        """
        cfg = self.config
        score = sentiment.score

        min_long = cfg.get("min_score_long", 0.1)
        min_short = cfg.get("min_score_short", -0.1)
        contrary_block = cfg.get("contrary_block", True)
        contrary_thresh = cfg.get("contrary_threshold", 0.3)

        if direction == "LONG":
            # Block if sentiment is too bearish
            if contrary_block and score < -contrary_thresh:
                return False
            # Need minimum bullish sentiment
            if score < min_long:
                return False
        elif direction == "SHORT":
            # Block if sentiment is too bullish
            if contrary_block and score > contrary_thresh:
                return False
            # Need minimum bearish sentiment
            if score > min_short:
                return False

        return True

    def get_size_multiplier(self, sentiment: CompositeSentiment, direction: str) -> float:
        """
        Get position size multiplier based on sentiment strength.
        Returns 1.0 for normal, up to strong_signal_multiplier for strong alignment.
        """
        cfg = self.config
        score = sentiment.score
        boost_thresh = cfg.get("strong_signal_boost", 0.3)
        boost_mult = cfg.get("strong_signal_multiplier", 1.5)

        if direction == "LONG" and score > boost_thresh:
            return boost_mult
        elif direction == "SHORT" and score < -boost_thresh:
            return boost_mult

        return 1.0

    def fetch_all_data(self) -> CompositeSentiment:
        """
        Fetch all sentiment data from available sources and compute composite.
        Uses yfinance for market data (DXY, US10Y, VIX, GLD).
        """
        readings = []

        try:
            import yfinance as yf

            # DXY
            try:
                dxy = yf.download("DX-Y.NYB", period="6mo", interval="1d", progress=False)
                if not dxy.empty:
                    readings.append(self.compute_dxy_sentiment(dxy["Close"].squeeze()))
            except Exception as e:
                logger.warning("Failed to fetch DXY: %s", e)
                readings.append(SentimentReading("dxy", 0.0, 0.0, self.weights["dxy"], stale=True))

            # US10Y
            try:
                us10y = yf.download("^TNX", period="6mo", interval="1d", progress=False)
                if not us10y.empty:
                    readings.append(self.compute_us10y_sentiment(us10y["Close"].squeeze()))
            except Exception as e:
                logger.warning("Failed to fetch US10Y: %s", e)
                readings.append(SentimentReading("us10y", 0.0, 0.0, self.weights["us10y"], stale=True))

            # VIX
            try:
                vix = yf.download("^VIX", period="6mo", interval="1d", progress=False)
                if not vix.empty:
                    readings.append(self.compute_vix_sentiment(vix["Close"].squeeze()))
            except Exception as e:
                logger.warning("Failed to fetch VIX: %s", e)
                readings.append(SentimentReading("vix", 0.0, 0.0, self.weights["vix"], stale=True))

            # GLD ETF flows
            try:
                gld = yf.download("GLD", period="3mo", interval="1d", progress=False)
                if not gld.empty:
                    readings.append(self.compute_etf_flow_sentiment(
                        gld["Volume"].squeeze(), gld["Close"].squeeze()))
            except Exception as e:
                logger.warning("Failed to fetch GLD: %s", e)
                readings.append(SentimentReading("etf_flows", 0.0, 0.0, self.weights["etf_flows"], stale=True))

        except ImportError:
            logger.warning("yfinance not installed. Sentiment data unavailable.")
            for source, weight in self.weights.items():
                readings.append(SentimentReading(source, 0.0, 0.0, weight, stale=True))

        # COT and Fear & Greed would require separate API calls
        # Add stale placeholders for now
        if not any(r.source == "cot" for r in readings):
            readings.append(SentimentReading("cot", 0.0, 0.0, self.weights.get("cot", 0.25), stale=True))
        if not any(r.source == "fear_greed" for r in readings):
            readings.append(SentimentReading("fear_greed", 50.0, 0.0, self.weights.get("fear_greed", 0.10), stale=True))

        return self.composite_score(readings)
