# oclw_bot

**oclw_bot** is an ICT-style backtesting and execution framework for XAUUSD (and other symbols). Parquet-based market data, modular ICT strategy modules (liquidity sweep, FVG, displacement, MSS, order blocks, etc.), and SQE-style strategies. **Current phase:** backtest + report loop; VPS/agent loop; optional Telegram (RUN_BACKTEST) and ML optimization (`oclw_bot optimize`).

**Voor actuele fase, wat er is gebouwd en hoe ermee te werken:** zie **docs/PROJECT_STATUS_GPT.md**.

## Structure

- **configs/** – YAML config (default, xauusd)
- **src/trader/** – Core: app, config, logging, io (parquet, cache), data (symbols, schema), indicators (ATR, EMA, swings), strategy_modules/ict, strategies (SQE), execution (risk, sizing, broker_stub), backtest (engine, metrics, report), **ml/** (config space, optimizer, rewards, knowledge base, continuous learning, features)
- **data/** – market_cache (XAUUSD 1h/15m parquet), signals
- **tests/** – unit, integration, regression, performance (+ smoke)
- **reports/latest/** – REPORT.md, metrics.json (per run)
- **reports/history/** – baseline.json (golden KPI reference)
- **logs/** – oclw_bot_<ts>.log (human); **logs/json/** – run_<ts>.json (ML)
- **artifacts/** – optional run_<ts>/ (metrics, report, equity) for Telegram/OpenClaw
- **scripts/** – setup_venv.py, run_full_test.py, run_tests.sh, run_backtest.sh, make_report.py, run_backtest_to_artifacts.py, telegram_listener.py
- **oclw_bot/** – rules.md, prompts (tester.md, improver.md) for the Test → Report → Improve loop
- **docs/** – PROJECT_STATUS_GPT.md (current phase), ARCHITECTURE.md, TODO.md, VPS_LOOP.md, TELEGRAM_COMMANDS.md, ARTIFACTS_SCHEMA.md

## Quick start

```bash
# Setup (recommended: one command)
python scripts/setup_venv.py
.\.venv\Scripts\Activate.ps1   # Windows
source .venv/bin/activate      # Linux

# Data + backtest
oclw_bot fetch
oclw_bot backtest --config configs/xauusd.yaml

# Full test + report
python scripts/run_full_test.py --days 30 --report

# ML optimization (local/experimental)
oclw_bot optimize --cycles 1 --candidates 5
```

See **RUN.md** for more commands.

## VPS Test → Report → Improve loop

1. **Run tests:** `./scripts/run_tests.sh` or `python -m pytest tests/ -v`
2. **Generate report:** `python scripts/make_report.py` → `reports/latest/REPORT.md` + `metrics.json`
3. **Set baseline (first time):** `python scripts/make_report.py --baseline` → `reports/history/baseline.json`
4. **oclw_bot agents:** Use `oclw_bot/rules.md` and `oclw_bot/prompts/tester.md` / `improver.md` for Tester- and Improver-Agent. Only accept changes when tests are green and KPIs stay within guardrails.

See **docs/VPS_LOOP.md** for full runbook and DoD. **Telegram:** `python scripts/telegram_listener.py` — RUN_BACKTEST returns report (docs/TELEGRAM_COMMANDS.md).

## Requirements

- Python 3.10+
- See `pyproject.toml` (or `requirements.txt`) for dependencies.
