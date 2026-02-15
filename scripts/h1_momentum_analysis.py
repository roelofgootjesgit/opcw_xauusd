"""
H1 momentum-veto analyse:
- Hoe vaak produceert H1 consecutive lower highs (LH seq)?
- Hoe vaak concurrent met bearish displacement?
- Wat is de outcome van M15 LONG entries tijdens LH seq vs niet?
- Symmetrisch: higher lows + bullish displacement vs SHORT entries.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import yaml

from src.trader.io.parquet_loader import load_parquet, ensure_data
from src.trader.strategy_modules.ict.structure_context import add_structure_context
from src.trader.strategy_modules.ict.displacement import DisplacementModule
from src.trader.strategies.sqe_xauusd import run_sqe_conditions, get_sqe_default_config
from src.trader.data.schema import calculate_rr

with open("configs/xauusd.yaml") as f:
    cfg = yaml.safe_load(f)

base_path = Path("data/market_cache")
struct_cfg = cfg.get("strategy", {}).get("structure_context", {"lookback": 30, "pivot_bars": 2})
disp_cfg = cfg.get("strategy", {}).get("displacement", {"min_body_pct": 60, "min_candles": 2, "min_move_pct": 1.5})

end = datetime.now()
start = end - timedelta(days=30)

data_1h = load_parquet(base_path, "XAUUSD", "1h", start=start, end=end)
data_15m = load_parquet(base_path, "XAUUSD", "15m", start=start, end=end)
if data_1h.empty or data_15m.empty:
    print("No data!")
    sys.exit(1)
data_1h = data_1h.sort_index()
data_15m = data_15m.sort_index()

# ========================================================
# STAP 1: H1 pivot highs/lows + LH/HL sequences
# ========================================================
data_1h = add_structure_context(data_1h, struct_cfg)

pivot_bars = struct_cfg.get("pivot_bars", 2)
high_roll = data_1h["high"].rolling(2 * pivot_bars + 1, center=True, min_periods=pivot_bars + 1).max()
low_roll = data_1h["low"].rolling(2 * pivot_bars + 1, center=True, min_periods=pivot_bars + 1).min()
is_ph = (data_1h["high"] == high_roll) & high_roll.notna()
is_pl = (data_1h["low"] == low_roll) & low_roll.notna()

# Build LH sequence tracker: at each bar, is the most recent swing high lower than the one before?
h1_lh_active = pd.Series(False, index=data_1h.index)  # consecutive lower highs
h1_hl_active = pd.Series(False, index=data_1h.index)  # consecutive higher lows

prev_sh = None
prev_prev_sh = None
prev_sl = None
prev_prev_sl = None

for i in range(len(data_1h)):
    if is_ph.iloc[i]:
        prev_prev_sh = prev_sh
        prev_sh = data_1h.iloc[i]["high"]
    if is_pl.iloc[i]:
        prev_prev_sl = prev_sl
        prev_sl = data_1h.iloc[i]["low"]

    if prev_sh is not None and prev_prev_sh is not None:
        h1_lh_active.iloc[i] = prev_sh < prev_prev_sh  # current SH < previous SH = LH
    if prev_sl is not None and prev_prev_sl is not None:
        h1_hl_active.iloc[i] = prev_sl > prev_prev_sl  # current SL > previous SL = HL

# ========================================================
# STAP 2: H1 displacement
# ========================================================
disp_mod = DisplacementModule()
data_1h_disp = disp_mod.calculate(data_1h, disp_cfg)
h1_bear_disp = data_1h_disp.get("bearish_disp", pd.Series(False, index=data_1h.index)).fillna(False)
h1_bull_disp = data_1h_disp.get("bullish_disp", pd.Series(False, index=data_1h.index)).fillna(False)

# Forward-fill displacement for a window (H1 disp active for next 3 H1 bars = ~3 hours)
h1_bear_disp_recent = h1_bear_disp.rolling(window=3, min_periods=1).max().fillna(0).astype(bool)
h1_bull_disp_recent = h1_bull_disp.rolling(window=3, min_periods=1).max().fillna(0).astype(bool)

# ========================================================
# STAP 3: Momentum-veto signals
# ========================================================
# LONG veto: H1 lower highs + bearish displacement
h1_long_veto = h1_lh_active & h1_bear_disp_recent
# SHORT veto: H1 higher lows + bullish displacement
h1_short_veto = h1_hl_active & h1_bull_disp_recent

print("=" * 70)
print("H1 MOMENTUM-VETO ANALYSE (30d)")
print("=" * 70)

print("\n--- H1 SIGNAL COUNTS ---")
print("  H1 bars total:          %d" % len(data_1h))
print("  Pivot highs:            %d" % int(is_ph.sum()))
print("  Pivot lows:             %d" % int(is_pl.sum()))
print("  LH active bars:         %d (%.0f%%)" % (int(h1_lh_active.sum()), 100*h1_lh_active.mean()))
print("  HL active bars:         %d (%.0f%%)" % (int(h1_hl_active.sum()), 100*h1_hl_active.mean()))
print("  H1 bearish disp:        %d" % int(h1_bear_disp.sum()))
print("  H1 bullish disp:        %d" % int(h1_bull_disp.sum()))
print("  Bear disp recent (3h):  %d" % int(h1_bear_disp_recent.sum()))
print("  Bull disp recent (3h):  %d" % int(h1_bull_disp_recent.sum()))
print("  LONG veto (LH+bear):    %d (%.0f%%)" % (int(h1_long_veto.sum()), 100*h1_long_veto.mean()))
print("  SHORT veto (HL+bull):   %d (%.0f%%)" % (int(h1_short_veto.sum()), 100*h1_short_veto.mean()))

# ========================================================
# STAP 4: Reindex veto signals to M15
# ========================================================
h1_long_veto_m15 = h1_long_veto.reindex(data_15m.index, method="ffill").fillna(False)
h1_short_veto_m15 = h1_short_veto.reindex(data_15m.index, method="ffill").fillna(False)
h1_lh_m15 = h1_lh_active.reindex(data_15m.index, method="ffill").fillna(False)
h1_hl_m15 = h1_hl_active.reindex(data_15m.index, method="ffill").fillna(False)

# ========================================================
# STAP 5: M15 entries + outcome per veto state
# ========================================================
sqe_cfg = get_sqe_default_config()
strategy_cfg = cfg.get("strategy", {}) or {}
for k, v in strategy_cfg.items():
    if isinstance(v, dict) and k in sqe_cfg and isinstance(sqe_cfg[k], dict):
        sqe_cfg[k].update(v)
    else:
        sqe_cfg[k] = v

long_entries = run_sqe_conditions(data_15m, "LONG", sqe_cfg)
short_entries = run_sqe_conditions(data_15m, "SHORT", sqe_cfg)

# Simulate trades for all entries (no dedup, no H1 gate - raw signal quality)
tp_r = cfg.get("backtest", {}).get("tp_r", 2.5)
sl_r = cfg.get("backtest", {}).get("sl_r", 1.0)

def simulate_quick(data, i, direction, tp_r, sl_r):
    entry = float(data.iloc[i]["close"])
    atr = (data["high"] - data["low"]).iloc[max(0, i-14):i+1].mean()
    if pd.isna(atr) or atr <= 0:
        atr = entry * 0.005
    if direction == "LONG":
        sl = entry - sl_r * atr
        tp = entry + tp_r * atr
    else:
        sl = entry + sl_r * atr
        tp = entry - tp_r * atr
    for j in range(i+1, min(i+100, len(data))):
        row = data.iloc[j]
        if direction == "LONG":
            if row["low"] <= sl:
                return -1.0, "LOSS"
            if row["high"] >= tp:
                return tp_r, "WIN"
        else:
            if row["high"] >= sl:
                return -1.0, "LOSS"
            if row["low"] <= tp:
                return tp_r, "WIN"
    return 0.0, "TIMEOUT"

print("\n--- M15 ENTRY OUTCOME vs H1 MOMENTUM STATE ---")

for direction, entries, veto_m15, lh_hl_m15, label in [
    ("LONG", long_entries, h1_long_veto_m15, h1_lh_m15, "LH"),
    ("SHORT", short_entries, h1_short_veto_m15, h1_hl_m15, "HL"),
]:
    entry_idx = [i for i in range(1, len(data_15m)-1) if entries.iloc[i]]
    results_veto = []      # entries during momentum veto
    results_lh_only = []   # entries during LH/HL but no displacement
    results_clean = []     # entries without LH/HL

    for i in entry_idx:
        r, outcome = simulate_quick(data_15m, i, direction, tp_r, sl_r)
        ts = data_15m.index[i]
        is_veto = bool(veto_m15.iloc[i])
        is_lh = bool(lh_hl_m15.iloc[i])

        if is_veto:
            results_veto.append((ts, r, outcome))
        elif is_lh:
            results_lh_only.append((ts, r, outcome))
        else:
            results_clean.append((ts, r, outcome))

    print("\n  %s entries: %d total" % (direction, len(entry_idx)))

    for group_name, group in [
        ("CLEAN (no %s)" % label, results_clean),
        ("%s only (no disp)" % label, results_lh_only),
        ("VETO (%s + disp)" % label, results_veto),
    ]:
        if not group:
            print("    %-25s: 0 trades" % group_name)
            continue
        wins = sum(1 for _, r, _ in group if r > 0)
        losses = sum(1 for _, r, _ in group if r < 0)
        total_r = sum(r for _, r, _ in group)
        avg_r = total_r / len(group)
        wr = wins / len(group) * 100
        print("    %-25s: %d trades | W=%d L=%d | WR=%.0f%% | tot_R=%.1f | avg_R=%.2f" % (
            group_name, len(group), wins, losses, wr, total_r, avg_r))
        # Show individual trades
        for ts, r, outcome in group:
            print("      %s | %.1fR | %s" % (ts, r, outcome))
