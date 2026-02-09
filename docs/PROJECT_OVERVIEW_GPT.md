# oclw_xauusd — Project Overview (helicopter view voor GPT)

Dit document geeft een overzicht van het project en **het verschil tussen lokaal werken en VPS**. Doel: lokaal testen, daarna pas pushen/pullen naar de VPS.

---

## Wat is dit project?

**oclw_bot** (opclw_xauusd) is een **deterministische** ICT-style execution/backtest-bot voor XAUUSD (goud).  
- Principe: **Meten → Wachten → Reageren** (geen voorspellen/gokken). Canonieke regels: **docs/OCLW_PRINCIPLES.md**.  
- Parquet-marketdata, modulaire ICT-modules (liquidity sweep, FVG, MSS, etc.), SQE-strategie in 3 pijlers (trend / liquiditeit / trigger).  
- Python 3.10+, CLI: `backtest`, `fetch`. Config via YAML + `.env`.

**Belangrijke mappen:**
- `configs/` — default.yaml, xauusd.yaml  
- `src/trader/` — app, config, backtest-engine, strategies, execution, indicators, strategy_modules/ict  
- `data/` — market_cache (Parquet), signals  
- `tests/` — unit, integration, regression, performance  
- `reports/latest/` — REPORT.md, metrics.json (per run)  
- `reports/history/` — baseline.json (gouden KPI-referentie)  
- `scripts/` — run_tests.sh, run_backtest.sh, make_report.py  
- `oclw_bot/` — rules.md, prompts (tester.md, improver.md) voor de Test → Report → Improve-loop  
- `docs/` — ARCHITECTURE.md, TODO.md, VPS_LOOP.md, deze overview  

---

## LOCAL vs VPS — overzicht

| Aspect | **LOCAL** | **VPS** |
|--------|-----------|---------|
| **Doel** | Ontwikkelen, experimenteren, tests draaien, backtest lokaal valideren | Geautomatiseerde Test → Report → Improve-loop; rapporten; eventueel live/paper later |
| **Data** | Zelf ophalen: `oclw_bot fetch` (Yahoo Finance → Parquet in `data/market_cache/XAUUSD/`) | Data moet op VPS staan (eerst `oclw_bot fetch` of eigen Parquet); kan via cron/script |
| **Workflow** | Wijzig code → run tests → run backtest → `make_report.py` → als alles ok: **push** | Pull → run tests + report → agents (Tester/Improver) → alleen accepteren als groen + KPI’s binnen guardrails |
| **Waar draaien** | Je eigen machine (Windows/Linux/macOS) | Externe server (Linux), vaak via cron of systemd |
| **.env / secrets** | Lokaal `.env` (niet committen); DATA_PATH, CACHE_TTL, optioneel YAHOO_* | Eigen `.env` op VPS; nooit dezelfde als lokaal committen |
| **Baseline** | Eerste keer lokaal: `make_report.py --baseline` kan; daarna baseline meestal op VPS/gedeeld | Baseline in `reports/history/baseline.json` is de referentie voor regressie |

---

## Workflow: lokaal testen → dan pas VPS

### Stap 1 — Lokaal (altijd eerst)

1. **Setup**  
   - **Aanbevolen:** `python scripts/setup_venv.py` → maakt `.venv`, installeert alles (incl. yfinance) in de venv, kopieert `.env`.  
   - Of handmatig: `python -m venv .venv` → activeren (Windows PS: `.\.venv\Scripts\Activate.ps1`, Linux: `source .venv/bin/activate`) → `pip install -e ".[yfinance]"`.  
   - `.env.example` kopiëren naar `.env` en aanpassen (setup_venv.py doet dit automatisch als .env nog niet bestaat).

2. **Data (lokaal)**  
   - `oclw_bot fetch` → haalt data via Yahoo (GC=F) en schrijft Parquet naar `data/market_cache/XAUUSD/`.  
   - Zonder fetch: backtest kan yfinance-fallback gebruiken als er geen Parquet is.

3. **Lokaal testen**  
   - Tests: `pytest tests/ -v --tb=short` of `./scripts/run_tests.sh`.  
   - Backtest: `oclw_bot backtest --config configs/xauusd.yaml`.  
   - Volledige ronde (zoals op VPS): `python scripts/make_report.py` → vult `reports/latest/REPORT.md` en `metrics.json`.

4. **Baseline (eenmalig of na grote wijziging)**  
   - Lokaal: `python scripts/make_report.py --baseline` → slaat huidige metrics op als `reports/history/baseline.json`.  
   - Regressietests vergelijken tegen deze baseline (o.a. winrate, trade count).

5. **Alleen als alles groen is en KPI’s ok**  
   - **Commit + push** naar de repo die de VPS gebruikt.

### Stap 2 — VPS (na push)

1. **Op de VPS:** `git pull` in de projectmap.
2. **Eerste keer op VPS:** venv en dependencies in de venv: `python3 scripts/setup_venv.py` → daarna `source .venv/bin/activate`. Bij volgende pulls alleen venv activeren; na grote wijzigingen eventueel opnieuw `pip install -e ".[yfinance]"` in de venv.
3. **Data op VPS:** Zorgen dat Parquet in `data/market_cache/XAUUSD/` staat (eenmalig `oclw_bot fetch` of eigen data).
4. **Rapport draaien:**  
   - `python scripts/make_report.py` (of via cron/systemd).  
   - Dit runt tests + backtest en schrijft again `reports/latest/REPORT.md` en `metrics.json`.
5. **Agents (Tester/Improver):** Gebruiken `oclw_bot/rules.md` en `oclw_bot/prompts/tester.md` / `improver.md`. Alleen wijzigingen accepteren als tests groen zijn en KPI’s binnen guardrails (geen slechtere max DD, PF boven minimum, geen overtrading).

**Belangrijk:**  
- **Lokaal** = plek om te breken en te fixen; **VPS** = plek waar de “officiële” run en rapporten en eventueel agents draaien.  
- **Nooit** wijzigingen alleen op de VPS doen zonder ze lokaal getest en gecommit te hebben; anders raken local en VPS uit sync.

---

## Scripts (lokaal én VPS)

| Script | Gebruik |
|--------|--------|
| **`python scripts/setup_venv.py`** | **Eerste keer (lokaal + VPS):** .venv aanmaken, alles in venv installeren (incl. yfinance), .env aanmaken. |
| **`python scripts/run_full_test.py`** | **Standaard alles-in-één:** check env, fetch Yahoo-data, backtest (default 30 dagen). Optioneel `--report` voor tests + REPORT.md. |
| `./scripts/run_tests.sh` | Alle tests (unit, integration, regression, performance). |
| `./scripts/run_backtest.sh [config]` | Backtest (default: configs/xauusd.yaml). |
| `python scripts/make_report.py` | Tests + backtest → `reports/latest/REPORT.md` + `metrics.json`. |
| `python scripts/make_report.py --baseline` | Zelfde + kopie naar `reports/history/baseline.json`. |

**Voorbeeld volle test (1 maand + rapport):**  
`python scripts/run_full_test.py --days 30 --report`

Op Windows: `run_tests.sh` / `run_backtest.sh` via Git Bash of WSL, of rechtstreeks:  
`pytest tests/ -v --tb=short` en `oclw_bot backtest --config configs/xauusd.yaml`.

---

## KPI’s en guardrails (VPS/lokaal hetzelfde)

- **KPI’s:** net_pnl, profit_factor, winrate, expectancy_r, max_drawdown, trade_count, avg_holding_hours.  
- **Geen change accepteren als:** max DD slechter, PF onder minimum, regressietests falen, trade count >20% stijging (overtrading).

---

## Config & env

- **configs/default.yaml** — symbol, timeframes, data paths, backtest defaults, risk, **logging.file_path** (standaard `logs/oclw_bot.log`).  
- **configs/xauusd.yaml** — XAUUSD-overrides (o.a. risk, strategy).  
- **.env** — DATA_PATH, CACHE_TTL_HOURS, optioneel YAHOO_*, broker (toekomst). Lokaal en VPS hebben elk hun eigen `.env`; `.env` wordt niet gecommit.

**Log + JSON per run:** elke testrun schrijft in **logs/** (projectmap):  
- **`.log`** (mens): `logs/oclw_bot_YYYY-MM-DD_HH-mm-ss.log` — leesbaar, voor debugging.  
- **`.json`** (ML): `logs/json/run_YYYY-MM-DD_HH-mm-ss.json` — gestructureerd (run_id, kpis, tests); ML leest JSON het beste.

---

## Handige commando’s (copy-paste)

```bash
# Eerste keer (lokaal of VPS): venv + alles in venv installeren
python scripts/setup_venv.py
.\.venv\Scripts\Activate.ps1   # Windows PS
source .venv/bin/activate      # Linux/VPS

# Lokaal: data + run
oclw_bot fetch
oclw_bot backtest --config configs/xauusd.yaml
python scripts/run_full_test.py --report
pytest tests/ -v --tb=short
python scripts/make_report.py
python scripts/make_report.py --baseline   # alleen wanneer baseline zetten

# VPS: na pull
python scripts/make_report.py
```

---

## Documentatie in repo

- **README.md** — projectintro, structuur, quick start.  
- **RUN.md** — setup, venv, Yahoo/fetch, CLI-modes, tests, config.  
- **docs/OCLW_PRINCIPLES.md** — canonieke regels (5 stappen, risk, sessies, wat nooit mag).  
- **docs/STRATEGY_BASIS.md** — 3 pijlers + mapping naar 5 stappen, roadmap.  
- **docs/SETTINGS.md** — waar settings staan (YAML + code) en hoe we ze bepalen (backtest, baseline, guardrails).  
- **docs/WERKWIJZE.md** — werkwijze: test draaien → rapport → vergelijken met baseline → beslissen → eventueel push/VPS.
- **docs/ARCHITECTURE.md** — data flow, uitbreiden (ICT-modules, strategies, broker).  
- **docs/VPS_LOOP.md** — VPS runbook, DoD, scripts, rapportformaat.  
- **docs/TODO.md** — open taken.  
- **docs/PROJECT_OVERVIEW_GPT.md** — dit bestand (helicopter view + local vs VPS).

Als je dit bestand in GPT plakt, heeft het voldoende context om het project en het verschil tussen lokaal testen en VPS te begrijpen.
