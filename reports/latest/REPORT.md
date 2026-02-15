# oclw_bot Report

**Run ID:** 2026-02-15 sweep  
**Git:** `903cd8d4f35d`  
**Status:** PASS — 365-day parallel sweep completed  
**Data source:** Dukascopy (spot XAUUSD, bid prices, UTC)

## Data

| Timeframe | Rows | Range |
|-----------|------|-------|
| 15m | 23,546 | 2025-02-17 — 2026-02-13 |
| 1h | 5,889 | 2025-02-17 — 2026-02-13 |

Fetched via `scripts/fetch_dukascopy_xauusd.py --days 365`.  
Cached in `data/market_cache/XAUUSD/{15m,1h}.parquet`.

## 365-Day Parallel Sweep Results

7 config variants tested in parallel (`scripts/parallel_sweep.py`).  
Regime detection computed once (2.4s for 23,546 bars).

| Config | Trades | WR% | PF | MaxDD(R) | Exp(R) | NetPnL$ |
|--------|--------|-----|------|----------|--------|---------|
| **tp_r_2.0** | **48** | **43.8** | **1.56** | **-4.0** | **+0.31** | **$247** |
| body_70 | 31 | 35.5 | 1.38 | -5.0 | +0.24 | $284 |
| tp_r_3.0 | 48 | 31.2 | 1.36 | -7.0 | +0.25 | $362 |
| baseline (tp_r=2.5) | 48 | 31.2 | 1.14 | -7.0 | +0.09 | $232 |
| move_1.0 | 48 | 31.2 | 1.14 | -7.0 | +0.09 | $232 |
| sweep_0.12 | 50 | 30.0 | 1.07 | -7.0 | +0.05 | $217 |
| lookback_7 | 17 | 17.6 | 0.54 | -10.0 | -0.38 | -$38 |

### Analyse

- **tp_r=2.0 is de duidelijke winnaar**: hoogste PF (1.56), laagste drawdown (-4R), beste expectancy (+0.31R/trade).
- Bij tp_r=2.0 is breakeven winrate 33.3%. Gerealiseerde winrate is 43.8% — ruim erboven.
- tp_r=3.0 levert meer netto PnL ($362) maar met dubbele drawdown (-7R) en lagere winrate (31.2%).
- body_70 (strengere displacement) werkt goed (PF=1.38) maar halveert het aantal trades (31 vs 48).
- lookback_7 triggerde de equity kill switch (-10R) — duidelijk te slecht.
- move_1.0 en sweep_0.12 gaven geen verbetering vs baseline.

### Conclusie

Over 365 dagen Dukascopy data presteert **tp_r=2.0** significant beter dan de huidige tp_r=2.5.
De hogere winrate (43.8% vs 31.2%) compenseert ruimschoots de kleinere TP per trade.

## Huidige config (configs/xauusd.yaml)

```yaml
backtest:
  tp_r: 2.5        # sweep suggereert 2.0
  sl_r: 1.0
strategy:
  displacement:
    min_body_pct: 60
    min_candles: 2
    min_move_pct: 1.5
  liquidity_sweep:
    sweep_threshold_pct: 0.15
    lookback_candles: 20
    reversal_candles: 4
  fair_value_gaps:
    min_gap_pct: 0.3
    validity_candles: 80
  require_structure: true
  structure_use_h1_gate: true
  entry_require_sweep_displacement_fvg: true
  entry_sweep_disp_fvg_lookback_bars: 5
  entry_sweep_disp_fvg_min_count: 2
```

## Sweep grid (geteste varianten)

| Label | Parameter | Waarde |
|-------|-----------|--------|
| baseline | (geen wijziging) | tp_r=2.5 |
| tp_r_2.0 | backtest.tp_r | 2.0 |
| tp_r_3.0 | backtest.tp_r | 3.0 |
| body_70 | strategy.displacement.min_body_pct | 70 |
| move_1.0 | strategy.displacement.min_move_pct | 1.0 |
| sweep_0.12 | strategy.liquidity_sweep.sweep_threshold_pct | 0.12 |
| lookback_7 | strategy.entry_sweep_disp_fvg_lookback_bars | 7 |

## Infrastructuur-wijzigingen (deze sessie)

1. **Dukascopy data loader** (`scripts/fetch_dukascopy_xauusd.py`) — vervangt OANDA/yfinance als databron
2. **Regime detector 20x versneld** — `_rolling_pct_rank()` numpy implementatie i.p.v. pandas `rolling().apply()`
3. **Regime caching** — 3-traps: precomputed > parquet cache > fresh compute
4. **Parallel sweep** (`scripts/parallel_sweep.py`) — meerdere configs tegelijk via multiprocessing

## Next actions

- Overweeg tp_r=2.0 toe te passen als nieuwe config (sterkste 365d resultaat).
- Eventueel body_70 combineren met tp_r=2.0 in een tweede sweep-ronde.
- Baseline opnieuw zetten na config-wijziging.
