"""
Multi-objective reward / fitness functions for strategy optimization.
"""
from typing import Any, Dict


def calculate_reward(metrics: Dict[str, Any], weights: Dict[str, float] | None = None) -> float:
    """
    Multi-objective reward combining:
    - Net PnL (in R): total_profit_r
    - Profit factor
    - Drawdown resistance: max(0, 1 + max_drawdown) so 0 dd -> 1, large dd -> 0
    - Win rate (0-1)

    Weights default: net_pnl 0.4, profit_factor 0.3, drawdown 0.2, win_rate 0.1.
    """
    w = weights or {
        "net_pnl": 0.4,
        "profit_factor": 0.3,
        "max_drawdown": 0.2,
        "win_rate": 0.1,
    }
    total_r = metrics.get("total_profit_r", 0.0) or 0.0
    pf = metrics.get("profit_factor", 0.0) or 0.0
    max_dd = metrics.get("max_drawdown", 0.0)
    # max_drawdown is stored as negative (e.g. -2.5); we want score in [0,1]
    drawdown_score = max(0.0, 1.0 + float(max_dd))
    win_rate_01 = metrics.get("win_rate_01", metrics.get("win_rate", 0.0) / 100.0) or 0.0
    if isinstance(win_rate_01, (int, float)) and win_rate_01 > 1:
        win_rate_01 = win_rate_01 / 100.0

    reward = (
        total_r * w.get("net_pnl", 0.4)
        + pf * w.get("profit_factor", 0.3)
        + drawdown_score * w.get("max_drawdown", 0.2)
        + win_rate_01 * w.get("win_rate", 0.1)
    )
    return float(reward)


def calculate_reward_from_trades(trades: list, weights: Dict[str, float] | None = None) -> float:
    """Compute metrics from trade list and return reward (convenience)."""
    from src.trader.backtest.metrics import compute_metrics

    metrics = compute_metrics(trades)
    return calculate_reward(metrics, weights)
