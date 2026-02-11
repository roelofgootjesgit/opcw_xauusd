# How to run oclw_bot

**Feb 2026.** Voor actuele fase en overzicht → **docs/PROJECT_STATUS_GPT.md**.

## Setup

1. **Projectmap** – ga naar de projectdirectory:
   ```bash
   cd path/to/opclw_xauusd
   ```

2. **Venv + alles installeren (aanbevolen)** – één commando voor venv, dependencies en optioneel .env:
   ```bash
   python scripts/setup_venv.py
   ```
   Dit maakt `.venv` aan (als die nog niet bestaat), installeert het project met `pip install -e ".[yfinance]"` **in de venv**, en kopieert `.env.example` naar `.env` als `.env` nog niet bestaat. Werkt lokaal (Windows/Linux) en op de VPS.

3. **Venv activeren** (na setup of bij een nieuwe shell):
   - Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
   - Windows (cmd): `.venv\Scripts\activate.bat`
   - Linux/VPS: `source .venv/bin/activate`  
   Daarna zie je `(.venv)` in je prompt.

4. **Handmatig (als je geen setup_venv.py wilt gebruiken):**
   ```bash
   python -m venv .venv
   # activeer venv (zie hierboven), dan:
   pip install -e ".[yfinance]"
   ```
   Copy `.env.example` naar `.env` en vul aan indien nodig.

5. **Data:** plaats Parquet in `data/market_cache/XAUUSD/` **of** gebruik Yahoo Finance (zie hieronder).

## Professioneel: bot testen op echte data (Yahoo Finance)

De aanbevolen manier om lokaal op data te testen is met **Yahoo Finance** (goud = GC=F, wordt als XAUUSD gebruikt). **Venv moet geactiveerd zijn** (zie Setup hierboven).

1. **Yahoo-afhankelijkheid** (in je venv):
   ```bash
   pip install -e .
   pip install yfinance
   ```
   Of in één keer: `pip install -e ".[yfinance]"`.

2. **Data ophalen** (alle timeframes uit config, standaard 15m + 1h)
   ```bash
   oclw_bot fetch
   ```
   Dit schrijft Parquet naar `data/market_cache/XAUUSD/` (15m.parquet, 1h.parquet).  
   Optioneel: `oclw_bot fetch --days 90` of `oclw_bot fetch -t 1h` voor één timeframe.

3. **Backtest draaien**
   ```bash
   oclw_bot backtest --config configs/xauusd.yaml
   ```
   Als er nog geen data is, probeert de backtest automatisch via Yahoo te laden (yfinance fallback).

4. **Volledige testronde (zoals op de VPS)**
   ```bash
   python scripts/make_report.py
   ```
   Draait pytest + backtest en schrijft `reports/latest/REPORT.md` en `metrics.json`.

**Kort flow:** `pip install yfinance` → `oclw_bot fetch` → `oclw_bot backtest` → eventueel `make_report.py`.

**Alles-in-één (aanbevolen voor een snelle test):**  
Eén script doet fetch + backtest (standaard 30 dagen) en optioneel tests + report:
```bash
python scripts/run_full_test.py
python scripts/run_full_test.py --days 30 --report
python scripts/run_full_test.py --skip-fetch   # alleen backtest op bestaande data
```
Elke testrun schrijft in **logs/**: .log voor mensen (`oclw_bot_YYYY-MM-DD_HH-mm-ss.log`), .json voor ML in **logs/json/** (`run_YYYY-MM-DD_HH-mm-ss.json`).

## Modes (CLI)

```bash
# Backtest (gebruikt cache of Yahoo-fallback als geen data)
oclw_bot backtest
oclw_bot backtest --config configs/xauusd.yaml

# Data ophalen: alle timeframes uit config (standaard 15m, 1h)
oclw_bot fetch
# Of expliciet:
oclw_bot fetch --symbol XAUUSD --timeframe 1h --days 90
oclw_bot fetch -s XAUUSD -t 15m -d 60

# ML-optimalisatie (learning cycle; lokaal/experimenteel)
oclw_bot optimize
oclw_bot optimize --cycles 2 --candidates 5
```

Zonder geïnstalleerd script:

```bash
python -m src.trader.app backtest --config configs/xauusd.yaml
python -m src.trader.app fetch
python -m src.trader.app optimize --cycles 1
```

## Tests

```bash
pytest tests/ -v --tb=short
# of alleen smoke:
pytest tests/test_sqe_smoke.py -v
```

## Config

- `configs/default.yaml` – default symbol, timeframes, paths.
- `configs/xauusd.yaml` – XAUUSD-overrides (symbol, risk, strategy params).
