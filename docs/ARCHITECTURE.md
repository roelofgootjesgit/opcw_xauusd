# oclw_bot Architecture

**Huidige status:** Zie **docs/PROJECT_STATUS_GPT.md** voor fase en wat er is gebouwd.

## Overview

- **CLI** (`src/trader/app.py`): modes `backtest`, `fetch`, **`optimize`** (ML learning cycle). Config via YAML + env.
- **Data**: Parquet under `data/market_cache/SYMBOL/TF.parquet`. Load/save in `io/parquet_loader.py`, optional in-memory `io/cache.py`.
- **Schema**: `data/schema.py` – `Trade`, `calculate_rr`. Symbols in `data/symbols.py`.
- **Indicators**: `indicators/` – ATR, EMA, swings (used by strategies and ICT modules).
- **Strategy modules**: `strategy_modules/base.py` + `strategy_modules/ict/*` – Liquidity Sweep, MSS, Displacement, FVG, Order Blocks, Breaker Blocks, Imbalance Zones, Structure Context, Structure Labels. Each implements `calculate()` and `check_entry_condition()`.
- **Strategies**: `strategies/sqe_xauusd.py` – SQE-style 3-pillar combo (trend_context, liquidity_levels, entry_trigger).
- **Execution**: `execution/risk.py`, `sizing.py`, `broker_stub.py` – risk limits, position size, placeholder broker.
- **Backtest**: `backtest/engine.py` loads data, runs SQE, records trades; `metrics.py` and `report.py` for summary.
- **Logging**: Per run: `logs/oclw_bot_<ts>.log` (human) and **`logs/json/run_<ts>.json`** (ML: run_id, git_commit, kpis). Optional **artifacts/run_<ts>/** (metrics.json, report.md, equity.csv) for Telegram/OpenClaw.
- **ML** (`ml/`): config_space, rewards, strategy_optimizer, knowledge_base, continuous_learning, features; used by `oclw_bot optimize`.

## Data flow

1. **Fetch**: `app fetch` → parquet_loader.ensure_data() → optional yfinance download → save Parquet.
2. **Backtest**: load_config → engine.run_backtest() → load_parquet → run_sqe_conditions → simulate TP/SL → list of Trade → metrics/report → write to reports/latest/ and logs/ (and optionally artifacts/).
3. **Optimize**: `app optimize` → ContinuousLearningAgent: fetch data → sample configs from config_space → run_backtest per config → rewards → update optimizer/knowledge_base → persist best to reports/latest/best_ml_config.json.
4. **Telegram**: telegram_listener receives RUN_BACKTEST → runs backtest (with lock) → writes logs/ + artifacts/run_<ts>/ → sends report to chat.

## Extending

- Add ICT module: new file in `strategy_modules/ict/`, subclass `BaseModule`, register if you add a registry.
- Add strategy: new file in `strategies/`, call ICT/indicators and return entry series or integrate in engine.
- Add broker: implement real orders in `execution/broker_stub.py` or new module, keep same interface.
