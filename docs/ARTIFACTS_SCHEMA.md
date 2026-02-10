# Artifacts schema (reports + data)

Elke backtest- of report-run schrijft **report als .log** en **data als .json** op vaste plekken. Optioneel (Telegram/OpenClaw) ook naar `artifacts/run_<ts>/`.

---

## Directory layout (canoniek)

```
logs/
  oclw_bot_2026-02-10_20-40-12.log   # Report (mens): zelfde formaat als andere runs
  json/
    run_2026-02-10_20-40-12.json     # Data (ML/verzameling): run_id, git_commit, kpis

artifacts/                            # Optioneel, o.a. voor Telegram
  .backtest.lock
  run_<ts>/
    metrics.json
    report.md
    equity.csv
```

**Naming:** `oclw_bot_YYYY-MM-DD_HH-MM-SS.log` en `run_YYYY-MM-DD_HH-MM-SS.json` (UTC).

---

## Bestanden

### logs/oclw_bot_<ts>.log

Report voor mensen: regels met run_id, Git, Config, KPIs-tabel (tekst). Zelfde naamconventie als overige run-logs.

### logs/json/run_<ts>.json

- **run_id** (str): ISO8601 UTC
- **git_commit** (str): eerste 12 tekens van HEAD
- **config** (str): gebruikte config path
- **kpis** (object): net_pnl, profit_factor, max_drawdown, winrate, win_rate_pct, expectancy_r, trade_count, avg_holding_hours
- Bij fout: **error** (str); kpis ontbreekt dan.

### artifacts/run_<ts>/ (optioneel)

- **metrics.json** — zelfde payload als logs/json/run_<ts>.json
- **report.md** —zelfde inhoud als .log (voor Telegram)
- **equity.csv**

| Kolom         | Beschrijving        |
|---------------|---------------------|
| timestamp     | Sluit-tijd van trade (ISO) |
| cumulative_r  | Cumulatieve PnL in R tot en met die trade |

(Alleen in artifacts/ bij gebruik van `--out`.)

---

## Reproduceerbaarheid

- Zelfde config +zelfde data (zelfde periode via default_period_days / data cache) → zelfde metrics.
- Run ID in metrics.json en report.md identificeert de run voor vergelijking en rollback.

---

## Waar gebruikt

- **make_report.py** (o.a. via deploy_check.sh) → report naar `logs/oclw_bot_<ts>.log`, data naar `logs/json/run_<ts>.json` + reports/latest/.
- **run_backtest.sh** → altijd report naar `logs/`, data naar `logs/json/`; met `--out` ook naar artifacts/ voor Telegram.
- **Telegram RUN_BACKTEST** → backtest + schrijft logs/ + logs/json/ + artifacts/run_<ts>/, stuurt report terug.
