"""
R:R sweep v2: test flat tp_r by DISABLING regime_profiles.
Also test: regime profiles ON vs OFF at various tp_r levels.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import yaml
from copy import deepcopy
from src.trader.backtest.engine import run_backtest

with open("configs/xauusd.yaml") as f:
    base_cfg = yaml.safe_load(f)

def metrics(trades):
    n = len(trades)
    if n == 0:
        return {"n": 0}
    wins = [t for t in trades if t.profit_r > 0]
    losses = [t for t in trades if t.profit_r < 0]
    net_r = sum(t.profit_r for t in trades)
    gross_win = sum(t.profit_r for t in wins) if wins else 0
    gross_loss = abs(sum(t.profit_r for t in losses)) if losses else 0.001
    pf = gross_win / gross_loss
    wr = len(wins) / n * 100
    avg_r = net_r / n
    equity = []
    cum = 0.0
    for t in trades:
        cum += t.profit_r
        equity.append(cum)
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    max_consec = 0.0
    streak = 0.0
    for t in trades:
        if t.profit_r < 0:
            streak += abs(t.profit_r)
            if streak > max_consec:
                max_consec = streak
        else:
            streak = 0.0
    win_rs = sorted([t.profit_r for t in wins], reverse=True)
    return {
        "n": n, "wr": wr, "pf": pf, "avg_r": avg_r, "net_r": net_r,
        "max_dd": -max_dd, "max_consec": max_consec,
        "win_rs": win_rs[:5],
        "regimes": {}
    }

def add_regime_info(trades):
    """Count regimes from trade objects."""
    r = {}
    for t in trades:
        reg = getattr(t, "regime", None) or "unknown"
        r[reg] = r.get(reg, 0) + 1
    return r

def print_row(label, m, marker=""):
    if m["n"] == 0:
        print("%-30s | %4d | %5s | %5s | %8s | %7s | %7s | %s" % (label, 0, "-", "-", "-", "-", "-", "-"))
        return
    wd = ", ".join(["%+.1f" % r for r in m["win_rs"]])
    print("%-30s | %4d | %4.1f%% | %5.2f | %+8.3f | %+7.2f | %6.2fR | %s%s" % (
        label, m["n"], m["wr"], m["pf"], m["avg_r"], m["net_r"], m["max_dd"], wd, marker))

print("=" * 110)
print("R:R SWEEP — REGIME PROFILES OFF vs ON")
print("=" * 110)
header = "%-30s | %4s | %5s | %5s | %8s | %7s | %7s | %s" % (
    "Scenario", "N", "WR%", "PF", "Expect_R", "Net_R", "Max_DD", "Win R detail")
print(header)
print("-" * 110)

# Test 1: Current config (regime profiles ON)
print("\n--- WITH REGIME PROFILES (current) ---")
trades_baseline = run_backtest(base_cfg)
m = metrics(trades_baseline)
print_row("Baseline (regime ON)", m, " <-- current")

# Show per-trade detail
print("\n  Per-trade detail:")
for t in trades_baseline:
    reg = getattr(t, "regime", "?")
    print("    %s | %-5s | %+.1fR | %-7s | regime=%s" % (
        t.timestamp_open.strftime("%Y-%m-%d %H:%M"), t.direction,
        t.profit_r, t.result, reg))

# Test 2: Regime profiles OFF, various flat tp_r
print("\n--- WITHOUT REGIME PROFILES (flat tp_r) ---")
print(header)
print("-" * 110)

for tp in [2.0, 2.5, 3.0, 3.5, 4.0]:
    cfg = deepcopy(base_cfg)
    cfg["regime_profiles"] = None  # disable regime profiles
    cfg["backtest"]["tp_r"] = tp
    cfg["backtest"]["sl_r"] = 1.0
    trades = run_backtest(cfg)
    m = metrics(trades)
    marker = " <-- base" if abs(tp - 2.5) < 0.01 else ""
    print_row("Flat tp_r=%.1f sl_r=1.0" % tp, m, marker)

# Test 3: Regime profiles OFF, flat higher R:R with tighter SL
print("\n--- FLAT WITH VARIED SL ---")
print(header)
print("-" * 110)

for tp, sl in [(3.0, 0.8), (3.0, 1.0), (3.5, 1.0), (3.0, 1.2)]:
    cfg = deepcopy(base_cfg)
    cfg["regime_profiles"] = None
    cfg["backtest"]["tp_r"] = tp
    cfg["backtest"]["sl_r"] = sl
    trades = run_backtest(cfg)
    m = metrics(trades)
    print_row("Flat tp=%.1f sl=%.1f (R:R=%.1f)" % (tp, sl, tp/sl), m)

print("\nDone.")
