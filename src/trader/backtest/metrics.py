"""
Backtest metrics: win rate, profit factor, expectancy, etc.
"""
from typing import List

from src.trader.data.schema import Trade


def compute_metrics(trades: List[Trade]) -> dict:
    if not trades:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "total_profit_r": 0.0,
        }
    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    total_r = sum(t.profit_r for t in trades)
    gross_profit = sum(t.profit_r for t in wins)
    gross_loss = abs(sum(t.profit_r for t in losses))
    pf = (gross_profit / gross_loss) if gross_loss else (gross_profit or 0.0)
    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (100.0 * len(wins) / len(trades)) if trades else 0.0,
        "profit_factor": pf,
        "expectancy": total_r / len(trades) if trades else 0.0,
        "total_profit_r": total_r,
    }
