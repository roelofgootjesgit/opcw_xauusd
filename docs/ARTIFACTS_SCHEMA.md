# Artifacts schema (reports + data)

**Feb 2026.** Zie **docs/PROJECT_STATUS_GPT.md** voor overzicht logs/artifacts-gebruik.

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
- **config_path** (str): gebruikte config path (bijv. configs/xauusd.yaml)
- **config** (str): idem, backwards compatibility
- **days** (int): backtest-periode in dagen
- **timeframes** (array): uit config (bijv. ["15m", "1h"])
- **symbol** (str): instrument (bijv. XAUUSD)
- **settings** (object): snapshot van trading-instellingen voor ML — alleen symbol, timeframes, backtest, risk, strategy (geen paden/env)
- **kpis** (object): net_pnl, profit_factor, max_drawdown, winrate, win_rate_pct, expectancy_r, trade_count, avg_holding_hours
- **tests** (object): passed, failed (indien van toepassing)
- Bij fout: **error** (str); kpis ontbreekt dan.

Met **settings** per run kunnen we datasets bouwen om trade settings te vergelijken over tijdspannen en timeframes; zie **docs/PLAN_LOGS_EN_SETTINGS_VOOR_ML.md**.

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
