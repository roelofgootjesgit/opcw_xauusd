"""
Context-aware sizing simulation.

Hypothesis: If we size LH-only LONG trades (and HL-only SHORT trades)
at reduced R, max_dd improves while preserving net edge.

Three scenarios:
  1. Baseline (all trades 1R)
  2. LH/HL trades at 0.5R
  3. LH/HL trades at 0.7R
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from copy import deepcopy
import yaml

from src.trader.backtest.engine import run_backtest
from src.trader.io.parquet_loader import load_parquet
from src.trader.strategy_modules.ict.structure_context import add_structure_context

# ── Load config ──
with open("configs/xauusd.yaml") as f:
    cfg = yaml.safe_load(f)

# ── Run actual backtest (baseline) ──
print("Running backtest...")
trades = run_backtest(cfg)
if not trades:
    print("0 trades. Abort.")
    sys.exit(1)
print("Baseline trades: %d" % len(trades))

# ── Load H1 data and compute LH/HL state ──
base_path = Path("data/market_cache")
struct_cfg = cfg.get("strategy", {}).get("structure_context", {"lookback": 30, "pivot_bars": 2})

end = datetime.now()
start = end - timedelta(days=30)
data_1h = load_parquet(base_path, "XAUUSD", "1h", start=start, end=end)
data_1h = data_1h.sort_index()
data_1h = add_structure_context(data_1h, struct_cfg)

# Detect pivot highs/lows
pivot_bars = struct_cfg.get("pivot_bars", 2)
high_roll = data_1h["high"].rolling(2 * pivot_bars + 1, center=True, min_periods=pivot_bars + 1).max()
low_roll = data_1h["low"].rolling(2 * pivot_bars + 1, center=True, min_periods=pivot_bars + 1).min()
is_ph = (data_1h["high"] == high_roll) & high_roll.notna()
is_pl = (data_1h["low"] == low_roll) & low_roll.notna()

# Build LH/HL state series
h1_lh_active = pd.Series(False, index=data_1h.index)
h1_hl_active = pd.Series(False, index=data_1h.index)

prev_sh, prev_prev_sh = None, None
prev_sl, prev_prev_sl = None, None

for i in range(len(data_1h)):
    if is_ph.iloc[i]:
        prev_prev_sh = prev_sh
        prev_sh = data_1h.iloc[i]["high"]
    if is_pl.iloc[i]:
        prev_prev_sl = prev_sl
        prev_sl = data_1h.iloc[i]["low"]
    if prev_sh is not None and prev_prev_sh is not None:
        h1_lh_active.iloc[i] = prev_sh < prev_prev_sh
    if prev_sl is not None and prev_prev_sl is not None:
        h1_hl_active.iloc[i] = prev_sl > prev_prev_sl


def get_h1_state(trade_ts, direction):
    """Return H1 state at trade entry time.
    Returns 'LH' if LONG during lower highs, 'HL' if SHORT during higher lows,
    'CLEAN' otherwise."""
    # Find most recent H1 bar <= trade timestamp
    h1_idx = data_1h.index[data_1h.index <= trade_ts]
    if len(h1_idx) == 0:
        return "CLEAN"
    latest_h1 = h1_idx[-1]
    if direction == "LONG" and h1_lh_active.loc[latest_h1]:
        return "LH"
    if direction == "SHORT" and h1_hl_active.loc[latest_h1]:
        return "HL"
    return "CLEAN"


# ── Map each trade to H1 state ──
trade_states = []
for t in trades:
    state = get_h1_state(t.timestamp_open, t.direction)
    trade_states.append(state)

# ── Compute metrics for a scenario ──
def compute_metrics(trades, states, scale_degraded):
    """Recompute metrics with scaled R for degraded trades."""
    scaled_rs = []
    for t, state in zip(trades, states):
        r = t.profit_r
        if state in ("LH", "HL"):
            r = r * scale_degraded
        scaled_rs.append(r)

    n = len(scaled_rs)
    wins = [r for r in scaled_rs if r > 0]
    losses = [r for r in scaled_rs if r < 0]
    net_r = sum(scaled_rs)
    gross_win = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0.001
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    wr = len(wins) / n * 100 if n > 0 else 0
    avg_r = net_r / n if n > 0 else 0

    # Max drawdown
    equity = []
    cum = 0.0
    for r in scaled_rs:
        cum += r
        equity.append(cum)
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd

    # DD clustering: max consecutive losses in R
    max_consec_loss_r = 0.0
    current_streak_r = 0.0
    for r in scaled_rs:
        if r < 0:
            current_streak_r += abs(r)
            if current_streak_r > max_consec_loss_r:
                max_consec_loss_r = current_streak_r
        else:
            current_streak_r = 0.0

    return {
        "trades": n,
        "net_r": net_r,
        "pf": pf,
        "wr": wr,
        "avg_r": avg_r,
        "max_dd": -max_dd,
        "max_consec_loss_r": max_consec_loss_r,
        "clean_trades": sum(1 for s in states if s == "CLEAN"),
        "degraded_trades": sum(1 for s in states if s in ("LH", "HL")),
    }


# ── Run scenarios ──
scenarios = {
    "Baseline (1.0R)": 1.0,
    "Degraded 0.5R":   0.5,
    "Degraded 0.7R":   0.7,
}

print("\n" + "=" * 80)
print("CONTEXT-AWARE SIZING SIMULATION")
print("=" * 80)

# Show trade breakdown first
print("\n--- TRADE H1-STATE BREAKDOWN ---")
for t, state in zip(trades, trade_states):
    r_str = "%+.1fR" % t.profit_r
    print("  %s | %-5s | %-5s | %s" % (
        t.timestamp_open.strftime("%Y-%m-%d %H:%M"),
        t.direction, state, r_str))

print("\n--- SCENARIO COMPARISON ---")
header = "%-20s | %6s | %7s | %5s | %6s | %7s | %8s | %12s" % (
    "Scenario", "Trades", "Net R", "PF", "WR%", "Avg R", "Max DD", "Max Loss Run")
print(header)
print("-" * len(header))

results = {}
for name, scale in scenarios.items():
    m = compute_metrics(trades, trade_states, scale)
    results[name] = m
    print("%-20s | %6d | %+7.2f | %5.2f | %5.1f%% | %+6.3f | %7.2fR | %11.2fR" % (
        name, m["trades"], m["net_r"], m["pf"], m["wr"], m["avg_r"],
        m["max_dd"], m["max_consec_loss_r"]))

print("\n--- TRADE DISTRIBUTION ---")
baseline = results["Baseline (1.0R)"]
print("  CLEAN trades:    %d" % baseline["clean_trades"])
print("  Degraded trades: %d" % baseline["degraded_trades"])

# ── Per-trade detail with scaled R ──
print("\n--- EQUITY CURVES (cumulative R) ---")
for name, scale in scenarios.items():
    cum = 0.0
    curve = []
    for t, state in zip(trades, trade_states):
        r = t.profit_r
        if state in ("LH", "HL"):
            r = r * scale
        cum += r
        curve.append(cum)
    # Show just key points: peak, trough, final
    peak_val = max(curve)
    trough_val = min(curve)
    peak_idx = curve.index(peak_val)
    trough_idx = curve.index(trough_val)
    print("  %-20s: peak=%+.2fR (trade #%d) | trough=%+.2fR (trade #%d) | final=%+.2fR" % (
        name, peak_val, peak_idx+1, trough_val, trough_idx+1, curve[-1]))

# ── Guardrail check ──
print("\n--- GUARDRAIL CHECK vs BASELINE ---")
b = results["Baseline (1.0R)"]
for name in ["Degraded 0.5R", "Degraded 0.7R"]:
    m = results[name]
    checks = []
    if m["max_dd"] < b["max_dd"]:  # more negative = worse
        checks.append("max_dd IMPROVED (%.2f -> %.2f)" % (b["max_dd"], m["max_dd"]))
    else:
        checks.append("max_dd SAME/WORSE (%.2f -> %.2f)" % (b["max_dd"], m["max_dd"]))
    if m["pf"] >= b["pf"]:
        checks.append("PF OK (%.2f -> %.2f)" % (b["pf"], m["pf"]))
    else:
        checks.append("PF WORSE (%.2f -> %.2f)" % (b["pf"], m["pf"]))
    if m["trades"] == b["trades"]:
        checks.append("trade_count UNCHANGED")
    print("  %s:" % name)
    for c in checks:
        print("    %s" % c)
    # Overall
    dd_better = m["max_dd"] > b["max_dd"]  # less negative = better
    pf_ok = m["pf"] >= b["pf"] * 0.95  # allow 5% tolerance
    verdict = "PASS" if dd_better and pf_ok else "REVIEW"
    print("    --> %s" % verdict)
