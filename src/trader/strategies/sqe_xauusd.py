"""
SQE (Smart Quality Entry) style strategy for XAUUSD.
Uses ICT concepts: liquidity sweep + displacement / FVG with optional MSS.
"""
from typing import List, Dict, Any
import pandas as pd

from src.trader.strategy_modules.ict.liquidity_sweep import LiquiditySweepModule
from src.trader.strategy_modules.ict.displacement import DisplacementModule
from src.trader.strategy_modules.ict.fair_value_gaps import FairValueGapModule
from src.trader.strategy_modules.ict.market_structure_shift import MarketStructureShiftModule


def get_sqe_default_config() -> Dict[str, Any]:
    return {
        "liquidity_sweep": {"lookback_candles": 20, "sweep_threshold_pct": 0.2, "reversal_candles": 3},
        "displacement": {"min_body_pct": 70, "min_candles": 3, "min_move_pct": 1.5},
        "fair_value_gaps": {"min_gap_pct": 0.5, "validity_candles": 50},
        "market_structure_shift": {"swing_lookback": 5, "break_threshold_pct": 0.2},
        "use_mss": True,
    }


def run_sqe_conditions(
    data: pd.DataFrame,
    direction: str,
    config: Dict[str, Any] | None = None,
) -> pd.Series:
    """
    Apply SQE modules and return a boolean series True where all selected conditions align.
    """
    cfg = config or get_sqe_default_config()
    df = data.copy()

    sweep_mod = LiquiditySweepModule()
    df = sweep_mod.calculate(df, cfg.get("liquidity_sweep", {}))
    disp_mod = DisplacementModule()
    df = disp_mod.calculate(df, cfg.get("displacement", {}))
    fvg_mod = FairValueGapModule()
    df = fvg_mod.calculate(df, cfg.get("fair_value_gaps", {}))

    sweep_ok = df["bullish_sweep"] if direction == "LONG" else df["bearish_sweep"]
    disp_ok = df["bullish_disp"] if direction == "LONG" else df["bearish_disp"]
    fvg_ok = df["in_bullish_fvg"] if direction == "LONG" else df["in_bearish_fvg"]
    combined = sweep_ok & disp_ok & fvg_ok

    if cfg.get("use_mss"):
        mss_mod = MarketStructureShiftModule()
        df = mss_mod.calculate(df, cfg.get("market_structure_shift", {}))
        mss_ok = df["bullish_mss"] if direction == "LONG" else df["bearish_mss"]
        combined = combined & mss_ok

    return combined.fillna(False)
