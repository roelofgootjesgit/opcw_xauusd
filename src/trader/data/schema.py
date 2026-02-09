"""
Data models: Trade, AnalysisResult, etc.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class Trade:
    timestamp_open: datetime
    timestamp_close: datetime
    symbol: str
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    exit_price: float
    sl: float
    tp: float
    profit_usd: float
    profit_r: float
    result: Literal["WIN", "LOSS", "TIMEOUT"]


def calculate_rr(entry: float, exit_price: float, sl: float, direction: str) -> float:
    if direction == "LONG":
        risk = abs(entry - sl)
        profit = exit_price - entry
    else:
        risk = abs(sl - entry)
        profit = entry - exit_price
    return (profit / risk) if risk else 0.0
