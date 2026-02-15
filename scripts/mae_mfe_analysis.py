"""
MAE/MFE analyse op alle trades (regime_profiles=null, flat tp_r=2.5 sl_r=1.0).

Per trade meten:
  - MAE (Maximum Adverse Excursion): hoe ver ging prijs tegen je voordat trade sloot
  - MFE (Maximum Favorable Excursion): hoe ver ging prijs in je richting voordat trade sloot
  - Beide in R-eenheden (genormaliseerd op SL-afstand)
  - Time to MFE: hoeveel bars tot maximale favorable move
  - Time to MAE: hoeveel bars tot maximale adverse move

Dit vertelt:
  - Of tp=2.5 realistisch is (MFE-distributie)
  - Of sl=1.0 te strak/te ruim is (MAE-distributie)
  - Of winners snel of langzaam bewegen
  - Of er ruimte is voor runners (MFE > 2.5R bij huidige verliezers?)
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

# Run backtest to get trades
trades = run_backtest(cfg)
if not trades:
    print("0 trades")
    sys.exit(1)

# Load M15 data
base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
period_days = cfg.get("backtest", {}).get("default_period_days", 90)
end = datetime.now()
start = end - timedelta(days=period_days)
data = load_parquet(base_path, "XAUUSD", "15m", start=start, end=end)
data = data.sort_index()

print("=" * 100)
print("MAE / MFE ANALYSE — %d trades, flat tp_r=2.5 sl_r=1.0" % len(trades))
print("=" * 100)

results = []

for t in trades:
    entry_price = t.entry_price
    sl = t.sl
    direction = t.direction

    # Risk in price terms
    if direction == "LONG":
        risk = entry_price - sl
    else:
        risk = sl - entry_price

    if risk <= 0:
        continue

    # Find entry bar index
    entry_mask = data.index >= t.timestamp_open
    exit_mask = data.index <= t.timestamp_close
    trade_bars = data[entry_mask & exit_mask]

    if trade_bars.empty:
        continue

    # Track MAE and MFE bar by bar
    mae_price = 0.0  # worst adverse move in price
    mfe_price = 0.0  # best favorable move in price
    mae_bar = 0
    mfe_bar = 0

    for idx, (bar_ts, bar) in enumerate(trade_bars.iterrows()):
        if direction == "LONG":
            adverse = entry_price - bar["low"]   # how far price dropped below entry
            favorable = bar["high"] - entry_price  # how far price rose above entry
        else:
            adverse = bar["high"] - entry_price   # how far price rose above entry
            favorable = entry_price - bar["low"]   # how far price dropped below entry

        if adverse > mae_price:
            mae_price = adverse
            mae_bar = idx
        if favorable > mfe_price:
            mfe_price = favorable
            mfe_bar = idx

    mae_r = mae_price / risk
    mfe_r = mfe_price / risk
    bars_total = len(trade_bars)
    hours_total = bars_total * 0.25  # 15min bars

    results.append({
        "ts": t.timestamp_open,
        "dir": direction,
        "result": t.result,
        "pnl_r": t.profit_r,
        "mae_r": mae_r,
        "mfe_r": mfe_r,
        "mae_bar": mae_bar,
        "mfe_bar": mfe_bar,
        "bars": bars_total,
        "hours": hours_total,
        "entry": entry_price,
        "sl": sl,
        "risk_usd": risk,
    })

# ── Print per-trade detail ──
print("\n--- PER-TRADE DETAIL ---")
header = "%-20s | %-5s | %-7s | %6s | %6s | %6s | %8s | %8s | %5s" % (
    "Entry time", "Dir", "Result", "PnL_R", "MAE_R", "MFE_R", "MAE@bar", "MFE@bar", "Bars")
print(header)
print("-" * len(header))

for r in results:
    print("%-20s | %-5s | %-7s | %+5.1fR | %5.2fR | %5.2fR | %7d | %7d | %5d" % (
        r["ts"].strftime("%Y-%m-%d %H:%M"),
        r["dir"], r["result"], r["pnl_r"],
        r["mae_r"], r["mfe_r"],
        r["mae_bar"], r["mfe_bar"], r["bars"]))

# ── Aggregate statistics ──
wins = [r for r in results if r["pnl_r"] > 0]
losses = [r for r in results if r["pnl_r"] < 0]

print("\n--- AGGREGATE STATISTICS ---")

def print_stats(label, group):
    if not group:
        print("  %s: 0 trades" % label)
        return
    maes = [r["mae_r"] for r in group]
    mfes = [r["mfe_r"] for r in group]
    bars_list = [r["bars"] for r in group]
    mfe_bars = [r["mfe_bar"] for r in group]
    mae_bars = [r["mae_bar"] for r in group]

    print("  %s (%d trades):" % (label, len(group)))
    print("    MAE:  mean=%.2fR  median=%.2fR  max=%.2fR" % (
        np.mean(maes), np.median(maes), np.max(maes)))
    print("    MFE:  mean=%.2fR  median=%.2fR  max=%.2fR" % (
        np.mean(mfes), np.median(mfes), np.max(mfes)))
    print("    Duration: mean=%.0f bars (%.1fh)  median=%.0f bars" % (
        np.mean(bars_list), np.mean(bars_list)*0.25, np.median(bars_list)))
    print("    Time to MFE: mean=bar %.0f  median=bar %.0f" % (
        np.mean(mfe_bars), np.median(mfe_bars)))
    print("    Time to MAE: mean=bar %.0f  median=bar %.0f" % (
        np.mean(mae_bars), np.median(mae_bars)))

print_stats("ALL", results)
print_stats("WINNERS", wins)
print_stats("LOSERS", losses)

# ── Key questions ──
print("\n--- KEY QUESTIONS ---")

# 1. Is tp=2.5 realistisch? Hoeveel trades bereiken 2.5R MFE?
reach_25 = sum(1 for r in results if r["mfe_r"] >= 2.5)
reach_30 = sum(1 for r in results if r["mfe_r"] >= 3.0)
reach_35 = sum(1 for r in results if r["mfe_r"] >= 3.5)
reach_40 = sum(1 for r in results if r["mfe_r"] >= 4.0)
print("\n  Q1: Hoeveel trades bereiken MFE >= X?")
print("    >= 2.5R: %d/%d (%.0f%%)" % (reach_25, len(results), 100*reach_25/len(results)))
print("    >= 3.0R: %d/%d (%.0f%%)" % (reach_30, len(results), 100*reach_30/len(results)))
print("    >= 3.5R: %d/%d (%.0f%%)" % (reach_35, len(results), 100*reach_35/len(results)))
print("    >= 4.0R: %d/%d (%.0f%%)" % (reach_40, len(results), 100*reach_40/len(results)))

# 2. Is sl=1.0 correct? Hoeveel winners hebben MAE > 0.8R?
winners_close_call = sum(1 for r in wins if r["mae_r"] > 0.8)
print("\n  Q2: Winners met MAE > 0.8R (bijna gestopt):")
print("    %d/%d winners" % (winners_close_call, len(wins)))
for r in wins:
    if r["mae_r"] > 0.8:
        print("      %s %s MAE=%.2fR MFE=%.2fR PnL=%+.1fR" % (
            r["ts"].strftime("%Y-%m-%d %H:%M"), r["dir"],
            r["mae_r"], r["mfe_r"], r["pnl_r"]))

# 3. Verliezers die winstgevend hadden kunnen zijn (MFE > 1.5R maar verloren)
losers_had_edge = [r for r in losses if r["mfe_r"] >= 1.5]
print("\n  Q3: Verliezers met MFE >= 1.5R (winst was er, maar niet gepakt):")
print("    %d/%d verliezers" % (len(losers_had_edge), len(losses)))
for r in losers_had_edge:
    print("      %s %s MAE=%.2fR MFE=%.2fR PnL=%+.1fR (piekte %+.1fR voor SL)" % (
        r["ts"].strftime("%Y-%m-%d %H:%M"), r["dir"],
        r["mae_r"], r["mfe_r"], r["pnl_r"], r["mfe_r"]))

# 4. Entry timing: MFE komt voor of na MAE?
mfe_before_mae = sum(1 for r in results if r["mfe_bar"] < r["mae_bar"])
mae_before_mfe = sum(1 for r in results if r["mae_bar"] < r["mfe_bar"])
simultaneous = sum(1 for r in results if r["mae_bar"] == r["mfe_bar"])
print("\n  Q4: Entry timing — gaat prijs eerst voor of tegen je?")
print("    MFE eerst (prijs beweegt meteen goed): %d/%d (%.0f%%)" % (
    mfe_before_mae, len(results), 100*mfe_before_mae/len(results)))
print("    MAE eerst (prijs gaat eerst tegen je):  %d/%d (%.0f%%)" % (
    mae_before_mfe, len(results), 100*mae_before_mfe/len(results)))

# 5. MFE distribution for all trades — what if TP was different?
print("\n  Q5: Wat als TP anders was? (MFE-based WR simulatie)")
for tp_test in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
    would_win = sum(1 for r in results if r["mfe_r"] >= tp_test)
    would_lose = len(results) - would_win
    net = would_win * tp_test - would_lose * 1.0
    wr_sim = would_win / len(results) * 100
    pf_sim = (would_win * tp_test) / (would_lose * 1.0) if would_lose > 0 else float("inf")
    exp_sim = net / len(results)
    print("    tp=%.1fR: WR=%.0f%% PF=%.2f E=%+.3fR Net=%+.1fR" % (
        tp_test, wr_sim, pf_sim, exp_sim, net))

print("\nDone.")
