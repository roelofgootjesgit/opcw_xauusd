"""
Correlation Monitor — DXY inverse check and S&P 500 risk-on/risk-off detection.

Key correlations for XAUUSD:
  - DXY (Dollar Index): typically inverse — strong dollar = bearish gold
  - S&P 500: mixed — risk-on = bearish gold, risk-off = bullish gold
  - US10Y: inverse — higher yields = bearish gold

When correlations break (e.g. XAUUSD and DXY both rising), it can signal
unusual market conditions that warrant caution.
"""
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CorrelationMonitor:
    """
    Monitor correlations between XAUUSD and related instruments.
    """

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.correlations: Dict[str, float] = {}
        self.alerts: list = []

    def compute_rolling_correlation(
        self,
        gold_returns: pd.Series,
        other_returns: pd.Series,
        lookback: Optional[int] = None,
    ) -> pd.Series:
        """Compute rolling correlation between gold and another series."""
        n = lookback or self.lookback
        return gold_returns.rolling(n).corr(other_returns)

    def check_dxy_correlation(
        self,
        gold_close: pd.Series,
        dxy_close: pd.Series,
    ) -> Dict:
        """
        Check DXY inverse correlation.
        Normal: negative correlation (gold up when dollar down).
        Warning: positive correlation (both moving same direction).
        """
        if gold_close is None or dxy_close is None:
            return {"status": "NO_DATA", "correlation": 0.0}
        if len(gold_close) < self.lookback or len(dxy_close) < self.lookback:
            return {"status": "INSUFFICIENT_DATA", "correlation": 0.0}

        gold_ret = gold_close.pct_change().dropna()
        dxy_ret = dxy_close.pct_change().dropna()

        # Align indices
        common = gold_ret.index.intersection(dxy_ret.index)
        if len(common) < self.lookback:
            return {"status": "INSUFFICIENT_DATA", "correlation": 0.0}

        gold_ret = gold_ret.loc[common]
        dxy_ret = dxy_ret.loc[common]

        corr = gold_ret.tail(self.lookback).corr(dxy_ret.tail(self.lookback))
        self.correlations["dxy"] = float(corr) if not np.isnan(corr) else 0.0

        # Normal: negative correlation
        if corr > 0.3:
            status = "WARNING"  # Unusual: gold and dollar moving same direction
            self.alerts.append(f"DXY correlation anomaly: {corr:.2f} (expected < 0)")
            logger.warning("DXY correlation anomaly: %.2f (normally negative)", corr)
        elif corr < -0.3:
            status = "NORMAL"  # Expected inverse correlation
        else:
            status = "WEAK"  # Weak correlation, normal variance

        return {
            "status": status,
            "correlation": round(float(corr), 3),
            "interpretation": "inverse" if corr < 0 else "positive" if corr > 0 else "neutral",
        }

    def check_sp500_correlation(
        self,
        gold_close: pd.Series,
        sp500_close: pd.Series,
    ) -> Dict:
        """
        Check S&P 500 correlation for risk-on/risk-off signal.
        Negative correlation = risk-off mode (gold as safe haven).
        Positive correlation = both risk assets rising (liquidity driven).
        """
        if gold_close is None or sp500_close is None:
            return {"status": "NO_DATA", "correlation": 0.0}
        if len(gold_close) < self.lookback or len(sp500_close) < self.lookback:
            return {"status": "INSUFFICIENT_DATA", "correlation": 0.0}

        gold_ret = gold_close.pct_change().dropna()
        sp_ret = sp500_close.pct_change().dropna()

        common = gold_ret.index.intersection(sp_ret.index)
        if len(common) < self.lookback:
            return {"status": "INSUFFICIENT_DATA", "correlation": 0.0}

        gold_ret = gold_ret.loc[common]
        sp_ret = sp_ret.loc[common]

        corr = gold_ret.tail(self.lookback).corr(sp_ret.tail(self.lookback))
        self.correlations["sp500"] = float(corr) if not np.isnan(corr) else 0.0

        if corr < -0.3:
            risk_mode = "RISK_OFF"  # Gold as safe haven
        elif corr > 0.3:
            risk_mode = "RISK_ON"  # Liquidity-driven rally
        else:
            risk_mode = "NEUTRAL"

        return {
            "status": risk_mode,
            "correlation": round(float(corr), 3),
            "interpretation": risk_mode.lower().replace("_", " "),
        }

    def full_check(
        self,
        gold_close: pd.Series,
        dxy_close: Optional[pd.Series] = None,
        sp500_close: Optional[pd.Series] = None,
    ) -> Dict:
        """Run all correlation checks."""
        result = {}

        if dxy_close is not None:
            result["dxy"] = self.check_dxy_correlation(gold_close, dxy_close)

        if sp500_close is not None:
            result["sp500"] = self.check_sp500_correlation(gold_close, sp500_close)

        # Overall risk assessment
        warnings = sum(1 for v in result.values() if v.get("status") == "WARNING")
        result["overall"] = {
            "warnings": warnings,
            "all_normal": warnings == 0,
            "correlations": dict(self.correlations),
        }

        return result

    def fetch_and_check(self, gold_close: pd.Series) -> Dict:
        """
        Fetch DXY and S&P 500 data via yfinance and run checks.
        Convenience method that handles data fetching.
        """
        dxy_close = None
        sp500_close = None

        try:
            import yfinance as yf

            dxy_data = yf.download("DX-Y.NYB", period="3mo", interval="1d", progress=False)
            if not dxy_data.empty:
                dxy_close = dxy_data["Close"].squeeze()

            sp_data = yf.download("^GSPC", period="3mo", interval="1d", progress=False)
            if not sp_data.empty:
                sp500_close = sp_data["Close"].squeeze()

        except ImportError:
            logger.warning("yfinance not available for correlation checks")
        except Exception as e:
            logger.warning("Failed to fetch correlation data: %s", e)

        return self.full_check(gold_close, dxy_close, sp500_close)

    def summary(self) -> Dict:
        """Get correlation monitoring summary."""
        return {
            "correlations": dict(self.correlations),
            "alerts": list(self.alerts[-10:]),  # Last 10 alerts
        }
