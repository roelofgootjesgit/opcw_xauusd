# OpenClaw

**OpenClaw** is an ICT-style backtesting and execution framework for XAUUSD (and other symbols). Parquet-based market data, modular ICT strategy modules (liquidity sweep, FVG, order blocks, etc.), and SQE-style strategies.

## Structure

- **configs/** – YAML config (default, xauusd)
- **src/trader/** – Core: app, config, logging, io (parquet, cache), data (symbols, schema), indicators (ATR, EMA, swings), strategy_modules/ict, strategies (SQE), execution (risk, sizing, broker_stub), backtest (engine, metrics, report)
- **data/** – market_cache (XAUUSD 1h/15m parquet), signals, reports
- **tests/** – Smoke and unit tests
- **docs/** – ARCHITECTURE.md, TODO.md

## Quick start

```bash
# Install (from project root)
pip install -e .

# Use OpenClaw CLI
openclaw backtest --config configs/xauusd.yaml
openclaw fetch --symbol XAUUSD --timeframe 15m

# Or via module
python -m src.trader.app backtest --config configs/xauusd.yaml
```

See **RUN.md** for more commands.

## Requirements

- Python 3.10+
- See `pyproject.toml` (or `requirements.txt`) for dependencies.
