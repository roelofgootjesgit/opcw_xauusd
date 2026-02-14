"""
Backtest metrics: win rate, profit factor, expectancy, max drawdown, etc.
Includes per-regime and per-direction breakdowns.
"""
from collections import defaultdict
from typing import Dict, List

from src.trader.data.schema import Trade


def _compute_core_metrics(trades: List[Trade]) -> dict:
    """Compute core metrics for a list of trades."""
    if not trades:
        return {
            "total_trades": 0,
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "win_rate_01": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "expectancy_r": 0.0,
            "total_profit_r": 0.0,
            "net_pnl": 0.0,
            "max_drawdown": 0.0,
            "avg_holding_hours": 0.0,
        }

    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    total_r = sum(t.profit_r for t in trades)
    gross_profit_r = sum(t.profit_r for t in wins)
    gross_loss_r = abs(sum(t.profit_r for t in losses))
    pf = (gross_profit_r / gross_loss_r) if gross_loss_r else (gross_profit_r or 0.0)
    net_pnl = sum(t.profit_usd for t in trades)
    win_rate_pct = 100.0 * len(wins) / len(trades)
    win_rate_01 = len(wins) / len(trades)
    expectancy_r = total_r / len(trades)

    # Equity curve (cumulative PnL in R) for max drawdown
    equity = []
    cum = 0.0
    for t in trades:
        cum += t.profit_r
        equity.append(cum)
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

    # Avg holding time in hours
    holding_seconds = [(t.timestamp_close - t.timestamp_open).total_seconds() for t in trades]
    avg_holding_hours = (sum(holding_seconds) / len(holding_seconds) / 3600.0) if holding_seconds else 0.0

    return {
        "total_trades": len(trades),
        "trade_count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate_pct,
        "win_rate_01": win_rate_01,
        "profit_factor": pf,
        "expectancy": expectancy_r,
        "expectancy_r": expectancy_r,
        "total_profit_r": total_r,
        "net_pnl": net_pnl,
        "max_drawdown": -max_dd,
        "avg_holding_hours": avg_holding_hours,
    }


def compute_metrics(trades: List[Trade]) -> dict:
    """Compute overall metrics (backward compatible)."""
    return _compute_core_metrics(trades)


def compute_metrics_by_direction(trades: List[Trade]) -> Dict[str, dict]:
    """Compute metrics split by LONG / SHORT."""
    by_dir: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        by_dir[t.direction].append(t)

    result = {}
    for direction in ["LONG", "SHORT"]:
        result[direction] = _compute_core_metrics(by_dir.get(direction, []))
    return result


def compute_metrics_by_regime(trades: List[Trade]) -> Dict[str, dict]:
    """
    Compute metrics split by regime.
    Requires trades to have the 'regime' field populated.
    """
    by_regime: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        regime = getattr(t, "regime", None) or "UNKNOWN"
        by_regime[regime].append(t)

    result = {}
    for regime, regime_trades in sorted(by_regime.items()):
        result[regime] = _compute_core_metrics(regime_trades)
    return result


def compute_metrics_by_session(trades: List[Trade]) -> Dict[str, dict]:
    """
    Compute metrics split by trading session.
    Requires trades to have the 'session' field populated.
    """
    by_session: Dict[str, List[Trade]] = defaultdict(list)
    for t in trades:
        session = getattr(t, "session", None) or "UNKNOWN"
        by_session[session].append(t)

    result = {}
    for session, session_trades in sorted(by_session.items()):
        result[session] = _compute_core_metrics(session_trades)
    return result


def compute_full_report(trades: List[Trade]) -> dict:
    """
    Compute comprehensive metrics report with all breakdowns.
    """
    return {
        "overall": compute_metrics(trades),
        "by_direction": compute_metrics_by_direction(trades),
        "by_regime": compute_metrics_by_regime(trades),
        "by_session": compute_metrics_by_session(trades),
    }
