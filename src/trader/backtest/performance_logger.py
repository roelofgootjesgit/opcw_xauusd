"""
Performance Logger — detailed trade logging with regime, sentiment, news labels.

Logs every trade with full context for analysis:
  - Direction, entry/exit, P&L
  - Regime at entry
  - Session
  - Sentiment score
  - News proximity
  - Spread
  - Order management events (BE, partial, trailing)

Outputs:
  - JSON per trade (machine readable)
  - Equity curve CSV
  - Weekly/monthly summary reports
"""
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.trader.data.schema import Trade

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
TRADE_LOG_DIR = ROOT / "logs" / "trades"
EQUITY_LOG_DIR = ROOT / "logs" / "equity"


def log_trade(
    trade: Trade,
    extra_context: Optional[Dict] = None,
) -> Path:
    """
    Log a single trade with full context to JSON.
    Returns path to the log file.
    """
    TRADE_LOG_DIR.mkdir(parents=True, exist_ok=True)

    ts = trade.timestamp_open.strftime("%Y%m%d_%H%M%S") if trade.timestamp_open else "unknown"
    filename = f"trade_{ts}_{trade.direction}_{trade.result}.json"

    record = {
        "timestamp_open": str(trade.timestamp_open),
        "timestamp_close": str(trade.timestamp_close),
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "sl": trade.sl,
        "tp": trade.tp,
        "profit_usd": round(trade.profit_usd, 2),
        "profit_r": round(trade.profit_r, 4),
        "result": trade.result,
        # Extended metadata
        "regime": getattr(trade, "regime", None),
        "session": getattr(trade, "session", None),
        "sentiment_score": getattr(trade, "sentiment_score", None),
        "news_proximity_min": getattr(trade, "news_proximity_min", None),
        "spread_at_entry": getattr(trade, "spread_at_entry", None),
    }

    if extra_context:
        record.update(extra_context)

    path = TRADE_LOG_DIR / filename
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return path


def log_equity_point(
    timestamp: datetime,
    balance: float,
    equity: float,
    drawdown_pct: float,
    regime: str = "",
    open_positions: int = 0,
) -> None:
    """Append an equity data point to the daily CSV."""
    EQUITY_LOG_DIR.mkdir(parents=True, exist_ok=True)

    date_str = timestamp.strftime("%Y-%m-%d")
    csv_file = EQUITY_LOG_DIR / f"equity_{date_str}.csv"

    file_exists = csv_file.exists()
    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "balance", "equity", "drawdown_pct", "regime", "open_positions"])
        writer.writerow([
            timestamp.isoformat(),
            round(balance, 2),
            round(equity, 2),
            round(drawdown_pct, 2),
            regime,
            open_positions,
        ])


def generate_period_summary(
    trades: List[Trade],
    period_label: str = "weekly",
) -> Dict:
    """
    Generate summary report for a period (daily/weekly/monthly).
    """
    if not trades:
        return {"period": period_label, "trade_count": 0}

    from src.trader.backtest.metrics import compute_full_report

    report = compute_full_report(trades)
    overall = report["overall"]

    # Regime breakdown
    regime_counts = {}
    for t in trades:
        regime = getattr(t, "regime", None) or "UNKNOWN"
        regime_counts[regime] = regime_counts.get(regime, 0) + 1

    # Session breakdown
    session_counts = {}
    for t in trades:
        session = getattr(t, "session", None) or "UNKNOWN"
        session_counts[session] = session_counts.get(session, 0) + 1

    summary = {
        "period": period_label,
        "date_range": {
            "start": str(min(t.timestamp_open for t in trades)),
            "end": str(max(t.timestamp_close for t in trades)),
        },
        "overall": overall,
        "by_direction": report.get("by_direction", {}),
        "by_regime": report.get("by_regime", {}),
        "regime_distribution": regime_counts,
        "session_distribution": session_counts,
        "longs": sum(1 for t in trades if t.direction == "LONG"),
        "shorts": sum(1 for t in trades if t.direction == "SHORT"),
    }

    return summary


def save_period_summary(summary: Dict, filename: Optional[str] = None) -> Path:
    """Save period summary to JSON."""
    reports_dir = ROOT / "reports" / "summaries"
    reports_dir.mkdir(parents=True, exist_ok=True)

    fname = filename or f"summary_{summary.get('period', 'unknown')}_{datetime.now().strftime('%Y%m%d')}.json"
    path = reports_dir / fname
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("Saved period summary: %s", path)
    return path
