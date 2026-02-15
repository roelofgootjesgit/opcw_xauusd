"""
Multi-window validation: regime_profiles=null met flat tp_r=2.5 sl_r=1.0.

Windows:
  - 30 dagen
  - 60 dagen
  - 90 dagen
  - 90 dagen split: eerste helft (dag 90-45) en tweede helft (dag 45-0)

Guardrails (alle windows moeten passen):
  - PF >= 1.4
  - Expectancy >= 0.2R
  - Max DD <= -5R (niet slechter dan -5R)
  - Trade count: rapporteer, geen hard reject

Verdict: ACCEPT alleen als alle windows passen.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import yaml
from copy import deepcopy
from datetime import datetime, timedelta
from src.trader.backtest.engine import run_backtest

with open("configs/xauusd.yaml") as f:
    base_cfg = yaml.safe_load(f)

# Verify regime_profiles is null
assert base_cfg.get("regime_profiles") is None, "regime_profiles should be null!"


def metrics(trades):
    n = len(trades)
    if n == 0:
        return {
            "n": 0, "wr": 0, "pf": 0, "avg_r": 0, "net_r": 0,
            "max_dd": 0, "max_consec": 0, "wins": 0, "losses": 0,
        }
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

    return {
        "n": n, "wr": wr, "pf": pf, "avg_r": avg_r, "net_r": net_r,
        "max_dd": -max_dd, "max_consec": max_consec,
        "wins": len(wins), "losses": len(losses),
    }


def run_window(label, period_days, start_offset_days=0):
    """Run backtest for a specific window."""
    cfg = deepcopy(base_cfg)
    cfg["backtest"]["default_period_days"] = period_days

    # If we need an offset (for split-half), adjust by temporarily
    # monkey-patching the data loading. Instead, we'll filter trades by date.
    trades = run_backtest(cfg)

    if start_offset_days > 0:
        # Filter: only keep trades from the offset window
        now = datetime.now()
        window_end = now - timedelta(days=start_offset_days)
        trades = [t for t in trades if t.timestamp_open <= window_end]

    m = metrics(trades)
    return m, trades


print("=" * 90)
print("MULTI-WINDOW VALIDATION: regime_profiles=null, flat tp_r=2.5 sl_r=1.0")
print("=" * 90)
print("Config: tp_r=%.1f, sl_r=%.1f, regime_profiles=%s" % (
    base_cfg["backtest"]["tp_r"],
    base_cfg["backtest"]["sl_r"],
    base_cfg.get("regime_profiles")))
print("Date: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))

# Guardrails
GUARD_PF = 1.4
GUARD_EXPECT = 0.2
GUARD_DD = -5.0

header = "%-20s | %4s | %4s | %5s | %5s | %8s | %7s | %7s | %s" % (
    "Window", "N", "W/L", "WR%", "PF", "Expect_R", "Net_R", "Max_DD", "Verdict")
print("\n" + header)
print("-" * len(header))

results = {}
all_pass = True

# Run each window
for label, days in [("30 dagen", 30), ("60 dagen", 60), ("90 dagen", 90)]:
    print("Running %s..." % label, end=" ", flush=True)
    m, trades = run_window(label, days)

    # Guardrail checks
    checks = []
    if m["n"] == 0:
        verdict = "FAIL (0 trades)"
        all_pass = False
    else:
        pf_ok = m["pf"] >= GUARD_PF
        exp_ok = m["avg_r"] >= GUARD_EXPECT
        dd_ok = m["max_dd"] >= GUARD_DD  # max_dd is negative, so >= means "not worse"
        if not pf_ok:
            checks.append("PF<%.1f" % GUARD_PF)
        if not exp_ok:
            checks.append("E<%.1f" % GUARD_EXPECT)
        if not dd_ok:
            checks.append("DD>%.1fR" % GUARD_DD)
        if checks:
            verdict = "FAIL (%s)" % ", ".join(checks)
            all_pass = False
        else:
            verdict = "PASS"

    print("\r%-20s | %4d | %d/%d | %4.1f%% | %5.2f | %+8.3f | %+7.2f | %6.2fR | %s" % (
        label, m["n"], m["wins"], m["losses"], m["wr"], m["pf"],
        m["avg_r"], m["net_r"], m["max_dd"], verdict))
    results[label] = m

# Split-half on 90d data
print("\nRunning 90d split-half...", flush=True)
cfg_90 = deepcopy(base_cfg)
cfg_90["backtest"]["default_period_days"] = 90
all_trades = run_backtest(cfg_90)

if all_trades:
    # Split by midpoint
    timestamps = [t.timestamp_open for t in all_trades]
    mid = min(timestamps) + (max(timestamps) - min(timestamps)) / 2
    first_half = [t for t in all_trades if t.timestamp_open <= mid]
    second_half = [t for t in all_trades if t.timestamp_open > mid]

    for label, subset in [("90d eerste helft", first_half), ("90d tweede helft", second_half)]:
        m = metrics(subset)
        checks = []
        if m["n"] == 0:
            verdict = "FAIL (0 trades)"
            all_pass = False
        elif m["n"] < 5:
            verdict = "WARN (N<%d)" % 5
            # Don't fail on split-half with very few trades
        else:
            pf_ok = m["pf"] >= GUARD_PF
            exp_ok = m["avg_r"] >= GUARD_EXPECT
            dd_ok = m["max_dd"] >= GUARD_DD
            if not pf_ok:
                checks.append("PF<%.1f" % GUARD_PF)
            if not exp_ok:
                checks.append("E<%.1f" % GUARD_EXPECT)
            if not dd_ok:
                checks.append("DD>%.1fR" % GUARD_DD)
            if checks:
                verdict = "FAIL (%s)" % ", ".join(checks)
                all_pass = False
            else:
                verdict = "PASS"

        print("%-20s | %4d | %d/%d | %4.1f%% | %5.2f | %+8.3f | %+7.2f | %6.2fR | %s" % (
            label, m["n"], m["wins"], m["losses"], m["wr"], m["pf"],
            m["avg_r"], m["net_r"], m["max_dd"], verdict))
        results[label] = m

# Per-trade detail (90d)
print("\n--- 90d TRADE DETAIL ---")
for t in all_trades:
    print("  %s | %-5s | %+.1fR | %s" % (
        t.timestamp_open.strftime("%Y-%m-%d %H:%M"),
        t.direction, t.profit_r, t.result))

# Final verdict
print("\n" + "=" * 90)
if all_pass:
    print("VERDICT: ACCEPT")
    print("Alle windows passen guardrails (PF>=%.1f, E>=%.1fR, DD>=%.1fR)" % (
        GUARD_PF, GUARD_EXPECT, GUARD_DD))
    print("Aanbeveling: regime_profiles=null behouden als nieuwe baseline.")
else:
    print("VERDICT: REJECT")
    print("Niet alle windows passen guardrails.")
    print("Aanbeveling: ROLLBACK regime_profiles in configs/xauusd.yaml.")
print("=" * 90)
