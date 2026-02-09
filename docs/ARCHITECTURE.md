# OpenClaw Architecture

## Overview

- **CLI** (`src/trader/app.py`): modes `backtest`, `fetch`. Config via YAML + env.
- **Data**: Parquet under `data/market_cache/SYMBOL/TF.parquet`. Load/save in `io/parquet_loader.py`, optional in-memory `io/cache.py`.
- **Schema**: `data/schema.py` – `Trade`, `calculate_rr`. Symbols in `data/symbols.py`.
- **Indicators**: `indicators/` – ATR, EMA, swings (used by strategies and ICT modules).
- **Strategy modules**: `strategy_modules/base.py` + `strategy_modules/ict/*` – Liquidity Sweep, MSS, Displacement, FVG, Order Blocks, Breaker Blocks, Imbalance Zones. Each implements `calculate()` and `check_entry_condition()`.
- **Strategies**: `strategies/sqe_xauusd.py` – SQE-style combo (sweep + displacement + FVG ± MSS).
- **Execution**: `execution/risk.py`, `sizing.py`, `broker_stub.py` – risk limits, position size, placeholder broker.
- **Backtest**: `backtest/engine.py` loads data, runs SQE, records trades; `metrics.py` and `report.py` for summary.

## Data flow

1. **Fetch**: `app fetch` → parquet_loader.ensure_data() → optional yfinance download → save Parquet.
2. **Backtest**: load_config → engine.run_backtest() → load_parquet → run_sqe_conditions → simulate TP/SL → list of Trade → metrics/report.

## Extending

- Add ICT module: new file in `strategy_modules/ict/`, subclass `BaseModule`, register if you add a registry.
- Add strategy: new file in `strategies/`, call ICT/indicators and return entry series or integrate in engine.
- Add broker: implement real orders in `execution/broker_stub.py` or new module, keep same interface.
