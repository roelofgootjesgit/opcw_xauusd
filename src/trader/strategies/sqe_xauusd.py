"""
SQE (Smart Quality Entry) for XAUUSD – 3-pillar model (prop/quant style).

The trade is determined by exactly 3 things:
  1. Trend context    – are we in the right structure/momentum?
  2. Liquidity/levels – are we at a level / did we sweep liquidity?
  3. Entry timing     – trigger: when do we actually enter?
"""
from typing import Dict, Any, List
import pandas as pd

from src.trader.strategy_modules.ict.liquidity_sweep import LiquiditySweepModule
from src.trader.strategy_modules.ict.displacement import DisplacementModule
from src.trader.strategy_modules.ict.fair_value_gaps import FairValueGapModule
from src.trader.strategy_modules.ict.market_structure_shift import MarketStructureShiftModule
from src.trader.strategy_modules.ict.structure_context import add_structure_context


# Module config keys (same as before, for backward compat)
DEFAULT_MODULE_CONFIG = {
    "liquidity_sweep": {"lookback_candles": 20, "sweep_threshold_pct": 0.2, "reversal_candles": 3},
    "displacement": {"min_body_pct": 70, "min_candles": 3, "min_move_pct": 1.5},
    "fair_value_gaps": {"min_gap_pct": 0.5, "validity_candles": 50},
    "market_structure_shift": {"swing_lookback": 5, "break_threshold_pct": 0.2},
    "structure_context": {"lookback": 30, "pivot_bars": 2},
}


def get_sqe_default_config() -> Dict[str, Any]:
    """Default config: 3 pillars + module params. Pillars define what feeds each bucket."""
    return {
        **DEFAULT_MODULE_CONFIG,
        # ---- 3 pillars (prop/quant) ----
        "trend_context": {
            "modules": ["market_structure_shift", "displacement"],  # structure + momentum
            "require_all": False,  # True = AND, False = OR
        },
        "liquidity_levels": {
            "modules": ["liquidity_sweep", "fair_value_gaps"],  # sweep + FVG levels
            "require_all": True,
        },
        "entry_trigger": {
            "module": "displacement",  # strong candle = trigger; alt: "liquidity_sweep" or "market_structure_shift"
        },
        # Alleen entries in expliciete structuur (HH/HL of LH/LL); RANGE blokkeren (OCLW_PRINCIPLES)
        "require_structure": True,
        # Stap 2: entry ALLEEN bij sweep + displacement + FVG (liquidity = target, niet entry)
        "entry_require_sweep_displacement_fvg": True,
        # Binnen N bars: sweep + displacement + FVG (0 = alleenzelfde bar, 5 = soepeler)
        "entry_sweep_disp_fvg_lookback_bars": 5,
    }


def _get_signal_series(df: pd.DataFrame, module: str, direction: str) -> pd.Series:
    """Map module name to boolean series for the given direction."""
    if direction == "LONG":
        key = {
            "liquidity_sweep": "bullish_sweep",
            "displacement": "bullish_disp",
            "fair_value_gaps": "in_bullish_fvg",
            "market_structure_shift": "bullish_mss",
        }.get(module)
    else:
        key = {
            "liquidity_sweep": "bearish_sweep",
            "displacement": "bearish_disp",
            "fair_value_gaps": "in_bearish_fvg",
            "market_structure_shift": "bearish_mss",
        }.get(module)
    if key and key in df.columns:
        return df[key].fillna(False)
    return pd.Series(False, index=df.index)


def _combine_pillar(df: pd.DataFrame, modules: List[str], require_all: bool, direction: str) -> pd.Series:
    """Combine multiple modules into one pillar (AND or OR)."""
    if not modules:
        return pd.Series(True, index=df.index)
    series = [_get_signal_series(df, m, direction) for m in modules]
    if require_all:
        out = series[0]
        for s in series[1:]:
            out = out & s
        return out
    out = series[0]
    for s in series[1:]:
        out = out | s
    return out


def run_sqe_conditions(
    data: pd.DataFrame,
    direction: str,
    config: Dict[str, Any] | None = None,
) -> pd.Series:
    """
    Run the 3-pillar model: Trend context + Liquidity/levels + Entry trigger.
    Returns a boolean series True where all three pillars align (entry valid).
    """
    cfg = config or get_sqe_default_config()
    df = data.copy()

    # Run all ICT modules (same params as before)
    sweep_mod = LiquiditySweepModule()
    df = sweep_mod.calculate(df, cfg.get("liquidity_sweep", {}))
    disp_mod = DisplacementModule()
    df = disp_mod.calculate(df, cfg.get("displacement", {}))
    fvg_mod = FairValueGapModule()
    df = fvg_mod.calculate(df, cfg.get("fair_value_gaps", {}))
    mss_mod = MarketStructureShiftModule()
    df = mss_mod.calculate(df, cfg.get("market_structure_shift", {}))

    # ---- Expliciete marktstructuur (HH/HL of LH/LL); RANGE = no trade ----
    df = add_structure_context(df, cfg.get("structure_context", {"lookback": 30, "pivot_bars": 2}))
    if cfg.get("require_structure", True):
        structure_ok = df["in_bullish_structure"] if direction == "LONG" else df["in_bearish_structure"]
    else:
        structure_ok = pd.Series(True, index=df.index)

    # ---- 1) Trend context ----
    tc_cfg = cfg.get("trend_context") or get_sqe_default_config()["trend_context"]
    trend_modules = tc_cfg.get("modules", ["market_structure_shift", "displacement"])
    trend_require_all = tc_cfg.get("require_all", False)
    trend_ok = _combine_pillar(df, trend_modules, trend_require_all, direction)

    # ---- 2) Liquidity / levels ----
    liq_cfg = cfg.get("liquidity_levels") or get_sqe_default_config()["liquidity_levels"]
    liq_modules = liq_cfg.get("modules", ["liquidity_sweep", "fair_value_gaps"])
    liq_require_all = liq_cfg.get("require_all", True)
    liquidity_ok = _combine_pillar(df, liq_modules, liq_require_all, direction)

    # ---- 3) Entry timing (trigger) ----
    trig_cfg = cfg.get("entry_trigger") or get_sqe_default_config()["entry_trigger"]
    trigger_module = trig_cfg.get("module", "displacement")
    trigger_ok = _get_signal_series(df, trigger_module, direction)

    # Stap 2: entry = structure + sweep + displacement + FVG (liquidity alleen als target)
    if cfg.get("entry_require_sweep_displacement_fvg", False):
        sweep_ok = _get_signal_series(df, "liquidity_sweep", direction)
        disp_ok = _get_signal_series(df, "displacement", direction)
        fvg_ok = _get_signal_series(df, "fair_value_gaps", direction)
        lookback = max(0, int(cfg.get("entry_sweep_disp_fvg_lookback_bars", 0)))
        min_count = max(1, min(3, int(cfg.get("entry_sweep_disp_fvg_min_count", 3))))  # 1–3
        if lookback > 0:
            window = lookback
            # rolling().max() geeft float; expliciet bool voor &/|
            sweep_recent = sweep_ok.rolling(window=window, min_periods=1).max().fillna(0).astype(bool)
            disp_recent = disp_ok.rolling(window=window, min_periods=1).max().fillna(0).astype(bool)
            fvg_recent = fvg_ok.rolling(window=window, min_periods=1).max().fillna(0).astype(bool)
            if min_count >= 3:
                combined = structure_ok & sweep_recent & disp_recent & fvg_recent
            elif min_count == 2:
                # Minstens 2 van 3 in het venster (soepeler)
                two_of_three = (sweep_recent & disp_recent) | (sweep_recent & fvg_recent) | (disp_recent & fvg_recent)
                combined = structure_ok & two_of_three
            else:
                combined = structure_ok & (sweep_recent | disp_recent | fvg_recent)
        else:
            if min_count >= 3:
                combined = structure_ok & sweep_ok & disp_ok & fvg_ok
            elif min_count == 2:
                two_of_three = (sweep_ok & disp_ok) | (sweep_ok & fvg_ok) | (disp_ok & fvg_ok)
                combined = structure_ok & two_of_three
            else:
                combined = structure_ok & (sweep_ok | disp_ok | fvg_ok)
    else:
        combined = trend_ok & liquidity_ok & trigger_ok & structure_ok

    return combined.fillna(False)
