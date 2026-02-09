"""
Position sizing: risk per trade (R), lot size from ATR/sl distance.
"""
from typing import Optional


def size_from_r(
    account_balance: float,
    risk_r: float = 1.0,
    risk_pct_per_r: float = 0.01,
) -> float:
    """
    Fraction of account to risk for this trade (as decimal).
    risk_pct_per_r: e.g. 0.01 = 1% of account per 1R.
    """
    return risk_r * risk_pct_per_r


def lot_size_from_sl_distance(
    account_balance: float,
    sl_distance_points: float,
    point_value: float = 1.0,
    risk_pct: float = 0.01,
) -> float:
    """
    Lot size so that sl_distance_points move = risk_pct of account.
    point_value: profit per point per lot (e.g. 1 for indices, 100 for gold per full point).
    """
    if sl_distance_points <= 0:
        return 0.0
    risk_amount = account_balance * risk_pct
    risk_per_lot = sl_distance_points * point_value
    return risk_amount / risk_per_lot if risk_per_lot else 0.0
