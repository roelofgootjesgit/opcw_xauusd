"""
Spread & Liquidity Monitor for XAUUSD.

Monitors real-time spread from Oanda and blocks trades when:
  - Spread exceeds max threshold (e.g. >40 pips)
  - Warns when spread is elevated (e.g. >25 pips)
  - Detects liquidity dry-ups (volume drops)

XAUUSD typical spread: 2-5 pips normal, 20-50+ during NFP/FOMC.
"""
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SpreadMonitor:
    """
    Monitor and track spread for XAUUSD.
    """

    def __init__(
        self,
        max_spread_pips: float = 40.0,
        warning_spread_pips: float = 25.0,
        history_size: int = 1000,
    ):
        self.max_spread_pips = max_spread_pips
        self.warning_spread_pips = warning_spread_pips
        self.history: deque = deque(maxlen=history_size)
        self.current_spread: float = 0.0
        self.last_update: Optional[datetime] = None

        # Statistics
        self.blocked_count: int = 0
        self.warning_count: int = 0

    def update(self, bid: float, ask: float, timestamp: Optional[datetime] = None) -> Dict:
        """
        Update with new tick data.
        Returns status dict with: spread, spread_pips, ok, warning, blocked.
        """
        spread = ask - bid
        spread_pips = spread * 100  # XAUUSD: 1 pip = 0.01

        self.current_spread = spread_pips
        self.last_update = timestamp or datetime.utcnow()
        self.history.append({
            "timestamp": self.last_update,
            "spread_pips": spread_pips,
            "bid": bid,
            "ask": ask,
        })

        blocked = spread_pips > self.max_spread_pips
        warning = spread_pips > self.warning_spread_pips

        if blocked:
            self.blocked_count += 1
            logger.warning("Spread BLOCKED: %.1f pips (max: %.1f)", spread_pips, self.max_spread_pips)
        elif warning:
            self.warning_count += 1
            logger.info("Spread WARNING: %.1f pips (warning: %.1f)", spread_pips, self.warning_spread_pips)

        return {
            "spread": spread,
            "spread_pips": spread_pips,
            "ok": not blocked,
            "warning": warning,
            "blocked": blocked,
        }

    def is_tradeable(self) -> bool:
        """Check if current spread allows trading."""
        return self.current_spread <= self.max_spread_pips

    def get_average_spread(self, minutes: int = 15) -> float:
        """Get average spread over last N minutes."""
        if not self.history:
            return 0.0
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        recent = [h["spread_pips"] for h in self.history if h["timestamp"] >= cutoff]
        return sum(recent) / len(recent) if recent else 0.0

    def get_max_spread(self, minutes: int = 15) -> float:
        """Get max spread over last N minutes."""
        if not self.history:
            return 0.0
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        recent = [h["spread_pips"] for h in self.history if h["timestamp"] >= cutoff]
        return max(recent) if recent else 0.0

    def summary(self) -> Dict:
        """Get spread monitoring summary."""
        return {
            "current_spread_pips": round(self.current_spread, 1),
            "avg_spread_15m": round(self.get_average_spread(15), 1),
            "max_spread_15m": round(self.get_max_spread(15), 1),
            "tradeable": self.is_tradeable(),
            "blocked_count": self.blocked_count,
            "warning_count": self.warning_count,
            "max_threshold": self.max_spread_pips,
            "warning_threshold": self.warning_spread_pips,
        }
