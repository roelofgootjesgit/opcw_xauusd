"""
Tijd-gebaseerde exit analyse.

Twee hypotheses testen op bestaande trades:

A) Time-stop: als na X bars MFE < threshold, exit (vroegtijdig verlies kappen)
B) Break-even stop: als MFE >= 1.5R bereikt, verplaats SL naar entry (BE)

Methode: per trade bar-voor-bar doorlopen, MAE/MFE bijhouden, en
simuleren wat er gebeurt onder verschillende exit-regels.

Geen code/config wijzigingen. Puur data-analyse.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from src.trader.backtest.engine import run_backtest
from src.trader.io.parquet_loader import load_parquet

with open("configs/xauusd.yaml") as f:
    cfg = yaml.safe_load(f)

trades = run_backtest(cfg)
if not trades:
    print("0 trades")
    sys.exit(1)

base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
period_days = cfg.get("backtest", {}).get("default_period_days", 90)
end = datetime.now()
start = end - timedelta(days=period_days)
data = load_parquet(base_path, "XAUUSD", "15m", start=start, end=end)
data = data.sort_index()

# ── Build bar-by-bar trade profiles ──
trade_profiles = []

for t in trades:
    entry_price = t.entry_price
    sl = t.sl
    tp = t.tp
    direction = t.direction

    if direction == "LONG":
        risk = entry_price - sl
    else:
        risk = sl - entry_price
    if risk <= 0:
        continue

    entry_mask = data.index >= t.timestamp_open
    exit_mask = data.index <= t.timestamp_close
    trade_bars = data[entry_mask & exit_mask]
    if trade_bars.empty:
        continue

    # Bar-by-bar tracking
    bar_data = []
    running_mae = 0.0
    running_mfe = 0.0
    for idx, (bar_ts, bar) in enumerate(trade_bars.iterrows()):
        if direction == "LONG":
            adverse = entry_price - bar["low"]
            favorable = bar["high"] - entry_price
            close_pnl = bar["close"] - entry_price
        else:
            adverse = bar["high"] - entry_price
            favorable = entry_price - bar["low"]
            close_pnl = entry_price - bar["close"]

        if adverse > running_mae:
            running_mae = adverse
        if favorable > running_mfe:
            running_mfe = favorable

        bar_data.append({
            "bar": idx,
            "mae_r": running_mae / risk,
            "mfe_r": running_mfe / risk,
            "close_pnl_r": close_pnl / risk,
            "low_r": -adverse / risk if direction == "LONG" else -adverse / risk,
            "high_r": favorable / risk,
        })

    trade_profiles.append({
        "ts": t.timestamp_open,
        "dir": direction,
        "result": t.result,
        "pnl_r": t.profit_r,
        "risk": risk,
        "entry": entry_price,
        "sl": sl,
        "tp": tp,
        "bars": bar_data,
        "total_bars": len(bar_data),
    })


def simulate_exit_rule(profiles, rule_fn, label):
    """Simulate an exit rule on all trades. rule_fn(bar_data, bar_idx) returns
    (exit, pnl_r) or None to continue."""
    results = []
    for p in profiles:
        exited_early = False
        exit_bar = p["total_bars"] - 1
        exit_pnl = p["pnl_r"]  # default: original outcome

        for i, bd in enumerate(p["bars"]):
            result = rule_fn(p, bd, i)
            if result is not None:
                exited_early = True
                exit_bar = i
                exit_pnl = result
                break

        results.append({
            "ts": p["ts"],
            "dir": p["dir"],
            "orig_result": p["result"],
            "orig_pnl": p["pnl_r"],
            "new_pnl": exit_pnl,
            "exit_bar": exit_bar,
            "early": exited_early,
        })
    return results


def print_comparison(label, sim_results, profiles):
    """Print comparison between original and simulated outcomes."""
    orig_net = sum(r["orig_pnl"] for r in sim_results)
    new_net = sum(r["new_pnl"] for r in sim_results)
    orig_wins = sum(1 for r in sim_results if r["orig_pnl"] > 0)
    new_wins = sum(1 for r in sim_results if r["new_pnl"] > 0)
    n = len(sim_results)
    early_exits = sum(1 for r in sim_results if r["early"])

    # PF
    new_gw = sum(r["new_pnl"] for r in sim_results if r["new_pnl"] > 0)
    new_gl = abs(sum(r["new_pnl"] for r in sim_results if r["new_pnl"] < 0))
    new_pf = new_gw / new_gl if new_gl > 0 else float("inf")

    orig_gw = sum(r["orig_pnl"] for r in sim_results if r["orig_pnl"] > 0)
    orig_gl = abs(sum(r["orig_pnl"] for r in sim_results if r["orig_pnl"] < 0))
    orig_pf = orig_gw / orig_gl if orig_gl > 0 else float("inf")

    # Max DD
    def calc_dd(pnl_list):
        cum = 0; peak = 0; mdd = 0
        for r in pnl_list:
            cum += r
            if cum > peak: peak = cum
            dd = peak - cum
            if dd > mdd: mdd = dd
        return -mdd

    orig_dd = calc_dd([r["orig_pnl"] for r in sim_results])
    new_dd = calc_dd([r["new_pnl"] for r in sim_results])

    print("\n  %s" % label)
    print("  " + "-" * 70)
    print("  %-25s | %10s | %10s | %8s" % ("", "Original", "Simulated", "Delta"))
    print("  %-25s | %10d | %10d | %+8d" % ("Trades", n, n, 0))
    print("  %-25s | %10d | %10d | %+8d" % ("Early exits", 0, early_exits, early_exits))
    print("  %-25s | %10d | %10d | %+8d" % ("Wins", orig_wins, new_wins, new_wins - orig_wins))
    print("  %-25s | %+10.2f | %+10.2f | %+8.2f" % ("Net R", orig_net, new_net, new_net - orig_net))
    print("  %-25s | %10.2f | %10.2f | %+8.2f" % ("PF", orig_pf, new_pf, new_pf - orig_pf))
    print("  %-25s | %10.3f | %10.3f | %+8.3f" % ("Expectancy R", orig_net/n, new_net/n, (new_net-orig_net)/n))
    print("  %-25s | %9.2fR | %9.2fR | %+7.2fR" % ("Max DD", orig_dd, new_dd, new_dd - orig_dd))

    # Show changed trades
    changed = [r for r in sim_results if abs(r["new_pnl"] - r["orig_pnl"]) > 0.01]
    if changed:
        print("\n  Gewijzigde trades:")
        for r in changed:
            print("    %s %-5s | orig=%+5.1fR -> new=%+5.1fR | exit@bar %d %s" % (
                r["ts"].strftime("%Y-%m-%d %H:%M"), r["dir"],
                r["orig_pnl"], r["new_pnl"], r["exit_bar"],
                "(early)" if r["early"] else ""))


print("=" * 90)
print("TIJD-GEBASEERDE EXIT ANALYSE — %d trades" % len(trade_profiles))
print("=" * 90)

# ══════════════════════════════════════════════════════════
# HYPOTHESE A: Time-stop
# Als na X bars MFE < threshold -> exit at close
# ══════════════════════════════════════════════════════════
print("\n\n### HYPOTHESE A: TIME-STOP ###")
print("Als na X bars MFE nog < threshold -> exit op slotkoers van die bar")

for max_bars, min_mfe in [(6, 0.5), (8, 0.5), (8, 0.3), (10, 0.5), (6, 0.3)]:
    def make_rule(mb, mm):
        def rule(profile, bar, i):
            if i == mb:
                if bar["mfe_r"] < mm:
                    return bar["close_pnl_r"]
            return None
        return rule

    sim = simulate_exit_rule(trade_profiles, make_rule(max_bars, min_mfe),
                             "Time-stop: %d bars, MFE<%.1fR" % (max_bars, min_mfe))
    print_comparison("Time-stop: exit@bar %d als MFE < %.1fR" % (max_bars, min_mfe), sim, trade_profiles)

# ══════════════════════════════════════════════════════════
# HYPOTHESE B: Break-even stop
# Als MFE >= threshold -> move SL naar entry (BE)
# ══════════════════════════════════════════════════════════
print("\n\n### HYPOTHESE B: BREAK-EVEN STOP ###")
print("Als MFE >= threshold -> SL naar entry. Trade kan dan alleen BE of TP worden.")

for be_threshold in [1.0, 1.5, 2.0]:
    def make_be_rule(threshold):
        def rule(profile, bar, i):
            # Check if we've reached the threshold at any previous bar
            if i > 0:
                prev_mfe = profile["bars"][i-1]["mfe_r"]
                if prev_mfe >= threshold:
                    # BE stop is active. Check if current bar touches entry
                    if bar["close_pnl_r"] <= 0:
                        # Check bar-by-bar: did low (for LONG) hit entry?
                        direction = profile["dir"]
                        entry = profile["entry"]
                        risk = profile["risk"]
                        bar_idx = data.index >= profile["ts"]
                        actual_bar = data.iloc[data.index.get_loc(data.index[bar_idx][i])]
                        if direction == "LONG" and actual_bar["low"] <= entry:
                            return 0.0  # BE exit
                        elif direction == "SHORT" and actual_bar["high"] >= entry:
                            return 0.0  # BE exit
            return None
        return rule

    sim = simulate_exit_rule(trade_profiles, make_be_rule(be_threshold),
                             "BE stop: move SL->BE at MFE %.1fR" % be_threshold)
    print_comparison("BE stop: SL->entry bij MFE >= %.1fR" % be_threshold, sim, trade_profiles)

# ══════════════════════════════════════════════════════════
# HYPOTHESE C: Combinatie — time-stop + BE
# ══════════════════════════════════════════════════════════
print("\n\n### HYPOTHESE C: COMBINATIE ###")
print("Time-stop + BE stop samen")

def combined_rule(profile, bar, i):
    # BE: als vorige bar MFE >= 1.5R en huidige bar raakt entry -> exit BE
    if i > 0:
        prev_mfe = profile["bars"][i-1]["mfe_r"]
        if prev_mfe >= 1.5:
            direction = profile["dir"]
            entry = profile["entry"]
            bar_idx = data.index >= profile["ts"]
            actual_bar = data.iloc[data.index.get_loc(data.index[bar_idx][i])]
            if direction == "LONG" and actual_bar["low"] <= entry:
                return 0.0
            elif direction == "SHORT" and actual_bar["high"] >= entry:
                return 0.0
    # Time-stop: bar 8, MFE < 0.5R -> exit
    if i == 8:
        if bar["mfe_r"] < 0.5:
            return bar["close_pnl_r"]
    return None

sim = simulate_exit_rule(trade_profiles, combined_rule,
                         "Combo: time-stop@8 + BE@1.5R")
print_comparison("Combo: time-stop@bar8 (MFE<0.5R) + BE@1.5R", sim, trade_profiles)

print("\n\nDone.")
