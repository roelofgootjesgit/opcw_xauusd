# oclw_bot

**oclw_bot** is an ICT-style backtesting and execution framework for XAUUSD (and other symbols). Parquet-based market data, modular ICT strategy modules (liquidity sweep, FVG, order blocks, etc.), and SQE-style strategies.

## Structure

- **configs/** – YAML config (default, xauusd)
- **src/trader/** – Core: app, config, logging, io (parquet, cache), data (symbols, schema), indicators (ATR, EMA, swings), strategy_modules/ict, strategies (SQE), execution (risk, sizing, broker_stub), backtest (engine, metrics, report)
- **data/** – market_cache (XAUUSD 1h/15m parquet), signals
- **tests/** – unit, integration, regression, performance (+ smoke)
- **reports/latest/** – REPORT.md, metrics.json (per run)
- **reports/history/** – baseline.json (golden KPI reference)
- **scripts/** – run_tests.sh, run_backtest.sh, make_report.py
- **oclw_bot/** – rules.md, prompts (tester.md, improver.md) for the Test → Report → Improve loop
- **docs/** – ARCHITECTURE.md, TODO.md, VPS_LOOP.md

## Quick start

```bash
# Install (from project root)
pip install -e .

# Use oclw_bot CLI
oclw_bot backtest --config configs/xauusd.yaml
oclw_bot fetch --symbol XAUUSD --timeframe 15m

# Or via module
python -m src.trader.app backtest --config configs/xauusd.yaml
```

See **RUN.md** for more commands.

## VPS Test → Report → Improve loop

1. **Run tests:** `./scripts/run_tests.sh` or `python -m pytest tests/ -v`
2. **Generate report:** `python scripts/make_report.py` → `reports/latest/REPORT.md` + `metrics.json`
3. **Set baseline (first time):** `python scripts/make_report.py --baseline` → `reports/history/baseline.json`
4. **oclw_bot agents:** Use `oclw_bot/rules.md` and `oclw_bot/prompts/tester.md` / `improver.md` for Tester- and Improver-Agent. Only accept changes when tests are green and KPIs stay within guardrails.

See **docs/VPS_LOOP.md** for full runbook and DoD.

## Requirements

- Python 3.10+
- See `pyproject.toml` (or `requirements.txt`) for dependencies.
