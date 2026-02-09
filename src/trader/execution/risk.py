"""
Risk limits: max position size, max daily loss in R.
"""
from typing import Optional


def check_max_daily_loss_r(
    daily_pnl_r: float,
    max_daily_loss_r: float = 3.0,
) -> bool:
    """True if daily loss is within limit (can trade)."""
    return daily_pnl_r >= -max_daily_loss_r


def check_max_position_pct(
    position_pct: float,
    max_position_pct: float = 0.02,
) -> bool:
    """True if position size is within limit."""
    return 0 <= position_pct <= max_position_pct
