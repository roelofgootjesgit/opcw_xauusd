# oclw_bot VPS: Test → Rapport → Verbeter Loop

## Doel

oclw_bot draait op een VPS en doorloopt automatisch:

1. **Tests aanmaken/uitbreiden** (Tester-Agent)
2. **Tests runnen**
3. **Rapport schrijven** (REPORT.md + metrics.json)
4. **Op basis van rapport verbeteringen doorvoeren** (Improver-Agent, met guardrails)
5. **Herhalen** tot alles groen is en KPI’s binnen marges vallen.

Guardrails: geen “random” aan de strategie sleutelen; alles via meetbare KPI’s en regressietests.

---

## Mappenstructuur (actueel)

```
opclw_xauusd/
  configs/           # default.yaml, xauusd.yaml
  data/              # market_cache, signals
  docs/              # ARCHITECTURE.md, TODO.md, VPS_LOOP.md
  oclw_bot/
    rules.md         # oclw_bot must-follow regels
    prompts/
      tester.md      # Tester-Agent prompt
      improver.md    # Improver-Agent prompt
  reports/
    latest/          # REPORT.md, metrics.json (per run)
    history/         # baseline.json (golden referentie)
  scripts/
    run_tests.sh     # pytest tests/
    run_backtest.sh  # oclw_bot backtest
    make_report.py   # genereert rapport + optioneel baseline
  src/trader/        # app, config, backtest, strategies, execution, ...
  tests/
    unit/            # indicators, signals, risk
    integration/     # pipeline, config, broker stub
    regression/      # baseline guardrails (winrate, trade count)
    performance/     # runtime limits
  pyproject.toml
  README.md
```

---

## Scripts

| Script | Doel |
|--------|------|
| **`python3 scripts/setup_venv.py`** | **Eerste keer (lokaal + VPS):** maak .venv, installeer `pip install -e ".[yfinance]"` in de venv, kopieer .env.example → .env. |
| `./scripts/run_tests.sh` | Run alle tests (unit, integration, regression, performance). |
| `./scripts/run_backtest.sh [config]` | Run backtest met config (default: configs/xauusd.yaml). |
| `python scripts/run_full_test.py` | Fetch + backtest (standaard 30 dagen); optie `--report` voor tests + rapport. |
| `python scripts/make_report.py` | Run tests + backtest, schrijf `reports/latest/REPORT.md` en `metrics.json`. |
| `python scripts/make_report.py --baseline` | Idem + kopieer naar `reports/history/baseline.json`. |

---

## Rapportformaat

- **reports/latest/REPORT.md** — Samenvatting (PASS/FAIL), failed tests (kort), KPI-tabel, next actions.
- **reports/latest/metrics.json** — run_id, git_commit, tests (passed/failed), kpis (net_pnl, profit_factor, max_drawdown, winrate, expectancy_r, trade_count, avg_holding_hours).

Baseline: **reports/history/baseline.json** —zelfde structuur; golden referentie voor regressie.

---

## KPI’s en guardrails

- **KPI’s:** net_pnl, profit_factor, winrate, expectancy_r, max_drawdown, trade_count, avg_holding_hours.
- **Geen change accepteren als:** max DD slechter, PF onder minimum, regressietests falen, trade count >20% stijging (overtrading).

---

## Definition of Done (DoD)

oclw_bot kan op de VPS:

- [x] Tests aanmaken/uitbreiden (Tester)
- [x] Tests draaien (`run_tests.sh` / pytest)
- [x] Rapport schrijven (`make_report.py`)
- [x] Verbeteringen doen met guardrails (Improver)
- [x] Alleen “accepteren” als alles groen is en KPI’s binnen guardrails

---

## VPS Runbook (kort)

### Eerste keer op VPS: venv en installatie

Alles in een venv installeren (zoals lokaal):

```bash
cd /path/to/opclw_xauusd
python3 scripts/setup_venv.py
source .venv/bin/activate
```

Daarna (eenmalig) data en baseline:

```bash
oclw_bot fetch --days 90
oclw_bot backtest --config configs/xauusd.yaml
python scripts/make_report.py --baseline
```

Bij elke `git pull` hoef je alleen de venv te activeren; dependencies zitten al in de venv. Na grote wijzigingen eventueel opnieuw: `pip install -e ".[yfinance]"` in de venv.

### Draaien

- **Systemd (optie):** service voor een runner-script dat periodiek `make_report.py` draait; logs naar bijv. `/var/log/opclaw/`. Gebruik de venv-Python: `/path/to/opclw_xauusd/.venv/bin/python scripts/make_report.py`.
- **Cron:** dagelijks of na push: `cd /path/to/opclw_xauusd && .venv/bin/python scripts/make_report.py` (zodat alles in de venv draait).
