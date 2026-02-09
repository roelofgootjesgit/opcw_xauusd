# How to run OpenClaw

## Setup

1. Copy `.env.example` to `.env` and set variables if needed.
2. Install: `pip install -e .` (this registers the `openclaw` command).
3. Place or generate Parquet data under `data/market_cache/XAUUSD/` (e.g. `1h.parquet`, `15m.parquet`).

## Modes (CLI)

Use the **openclaw** command after install:

```bash
# Backtest with default config
openclaw backtest

# Backtest with XAUUSD config
openclaw backtest --config configs/xauusd.yaml

# Download/cache data only
openclaw fetch --symbol XAUUSD --timeframe 15m
openclaw fetch -s XAUUSD -t 1h -d 90
```

Alternative (without installing the script):

```bash
python -m src.trader.app backtest --config configs/xauusd.yaml
python -m src.trader.app fetch --symbol XAUUSD --timeframe 15m
```

Tests:

```bash
pytest tests/test_sqe_smoke.py -v
```

## Config

- `configs/default.yaml` – default symbol, timeframes, paths.
- `configs/xauusd.yaml` – XAUUSD-specific overrides (symbol, risk, strategy params).
