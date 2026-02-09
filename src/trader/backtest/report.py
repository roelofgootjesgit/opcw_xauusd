"""
Simple text report from backtest results.
"""
from typing import List

from src.trader.data.schema import Trade
from src.trader.backtest.metrics import compute_metrics


def report_text(trades: List[Trade], title: str = "Backtest Report") -> str:
    m = compute_metrics(trades)
    lines = [
        f"=== {title} ===",
        f"Total trades: {m['total_trades']}",
        f"Wins: {m['wins']} | Losses: {m['losses']}",
        f"Win rate: {m['win_rate']:.1f}%",
        f"Profit factor: {m['profit_factor']:.2f}",
        f"Expectancy: {m['expectancy']:.2f}R",
        f"Total P&L: {m['total_profit_r']:.2f}R",
    ]
    return "\n".join(lines)
