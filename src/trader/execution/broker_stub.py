"""
Broker stub – placeholder for MT5 / Oanda / etc.
"""
from typing import Literal
from dataclasses import dataclass


@dataclass
class OrderRequest:
    symbol: str
    direction: Literal["BUY", "SELL"]
    volume: float
    sl: float
    tp: float
    comment: str = ""


def submit_order(req: OrderRequest) -> bool:
    """Stub: log and return True. Replace with real broker API."""
    print(f"[BROKER_STUB] Would send: {req.direction} {req.symbol} vol={req.volume} sl={req.sl} tp={req.tp}")
    return True
