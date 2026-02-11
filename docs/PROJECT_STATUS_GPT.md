# oclw_xauusd — Huidige status (voor GPT / Feb 2026)

**Doel van dit document:** Eén plek waar staat **in welke fase we zitten**, **wat er is gebouwd** en **hoe je ermee werkt**. Gebruik dit in GPT als basis-context naast de andere docs.

---

## 1. Huidige fase

We zitten in de **backtest- en rapport-fase** met **VPS/agent-loop** en **optionele ML-optimalisatie**.

| Aspect | Status |
|--------|--------|
| **Data** | Parquet in `data/market_cache/XAUUSD/`; fetch via Yahoo (GC=F) of eigen data. |
| **Strategie** | SQE (3 pijlers: trend_context, liquidity_levels, entry_trigger) met ICT-modules; **alleen LONG** in engine (short = TODO). |
| **Backtest** | Draait stabiel; TP/SL in R; metrics + report naar `reports/latest/` en `logs/`. |
| **Rapport + baseline** | `make_report.py` → REPORT.md + metrics.json; baseline in `reports/history/baseline.json` voor regressie. |
| **VPS-loop** | Tester + Improver agents (rules in `oclw_bot/rules.md`); alleen wijzigingen accepteren binnen guardrails. |
| **Telegram** | `telegram_listener.py`: RUN_BACKTEST → backtest → report terug; lock tegen dubbele runs. |
| **ML** | Config space, rewards, strategy_optimizer, knowledge_base, continuous_learning, features; CLI `oclw_bot optimize`; nog niet in VPS-loop geïntegreerd. |
| **Live/paper** | Niet; broker = stub. MT5/Oanda = TODO. |

**Kort:** Lokaal en op VPS: fetch → backtest → rapport → vergelijken met baseline → alleen groen + guardrails accepteren. Telegram voor on-demand backtest; ML voor lokaal/experimenteel optimaliseren.

---

## 2. Wat is er gebouwd (overzicht)

### 2.1 Kern

- **CLI** `oclw_bot`: `backtest`, `fetch`, `optimize` (ML learning cycle).
- **Config:** YAML (`configs/default.yaml`, `configs/xauusd.yaml`) + `.env` (DATA_PATH, CACHE_TTL, YAHOO_*, TELEGRAM_BOT_TOKEN).
- **Data:** `io/parquet_loader.py` (Yahoo → Parquet), `io/cache.py`; schema in `data/schema.py`, symbols in `data/symbols.py`.
- **Indicators:** ATR, EMA, swings (`indicators/`).
- **ICT-modules** (`strategy_modules/ict/`): liquidity_sweep, displacement, fair_value_gaps, market_structure_shift, order_blocks, breaker_blocks, imbalance_zones, structure_context, structure_labels.
- **Strategie:** `strategies/sqe_xauusd.py` — 3 pijlers (trend / liquiditeit / trigger), OR/AND per pijler, `require_structure`, `structure_use_h1_gate`, `entry_require_sweep_displacement_fvg`, enz.
- **Execution:** risk, sizing, broker_stub (geen echte broker).
- **Backtest:** `backtest/engine.py` → trades → `metrics.py` + `report.py`.

### 2.2 Rapport, logs, artifacts

- **reports/latest/** — REPORT.md, metrics.json (per run).
- **reports/history/** — baseline.json (gouden KPI-referentie).
- **logs/** — `oclw_bot_YYYY-MM-DD_HH-mm-ss.log` (mens); **logs/json/** — `run_YYYY-MM-DD_HH-mm-ss.json` (ML).
- **artifacts/** (optioneel): `run_<ts>/` met metrics.json, report.md, equity.csv (bij `run_backtest.sh --out` of Telegram RUN_BACKTEST).

### 2.3 Scripts

| Script | Doel |
|--------|------|
| `python scripts/setup_venv.py` | Eerste keer: .venv, pip install in venv, .env van example. |
| `python scripts/run_full_test.py [--days N] [--report] [--skip-fetch]` | Fetch + backtest (+ optioneel pytest + report). |
| `python scripts/make_report.py [--baseline]` | Tests + backtest → reports/latest/ (+ baseline kopie). |
| `./scripts/run_tests.sh` | pytest tests/. |
| `./scripts/run_backtest.sh [config] [--out dir]` | Alleen backtest; met --out ook artifacts. |
| `python scripts/run_backtest_to_artifacts.py` | Backtest → metrics + report + equity in artifacts/run_<ts>/. |
| `python scripts/telegram_listener.py` | Telegram: RUN_BACKTEST → report terug (zie docs/TELEGRAM_COMMANDS.md). |
| `./scripts/deploy_check.sh` | Gate na pull: venv + pytest + make_report. |

### 2.4 ML (`src/trader/ml/`)

- **config_space.py** — search space voor SQE-params; `sample_config()`, `config_to_backtest_cfg()`.
- **rewards.py** — multi-objective reward (net_pnl, PF, drawdown, winrate).
- **strategy_optimizer.py** — Thompson-Sampling-achtige optimalisatie; candidate configs, backtest-eval, best config.
- **knowledge_base.py** — genealogie van configs, succesvolle configs bewaren.
- **continuous_learning.py** — ContinuousLearningAgent: data ophalen → N candidates evalueren → optimizer + KB updaten → best config naar `reports/latest/best_ml_config.json`.
- **features/** — FeatureExtractionPipeline (market_structure, liquidity, technical, statistical) voor toekomstige regime/entry-ML.

**CLI:** `oclw_bot optimize [--cycles N] [--candidates M]` draait learning cycle(s). Nog niet gekoppeld aan Improver/VPS.

### 2.5 Agents (VPS)

- **oclw_bot/rules.md** — regels voor Tester en Improver (guardrails, max 1–3 changes, geen overfit).
- **oclw_bot/prompts/tester.md** — Tester-Agent (tests, rapport).
- **oclw_bot/prompts/improver.md** — Improver-Agent (rapport lezen, kleine fixes/parameters, alleen binnen guardrails).

---

## 3. Hoe ermee te werken

### 3.1 Lokaal (aanbevolen volgorde)

1. **Setup (eenmalig):** `python scripts/setup_venv.py` → venv activeren (Windows: `.\.venv\Scripts\Activate.ps1`).
2. **Data:** `oclw_bot fetch` (of `run_full_test.py` doet fetch zelf).
3. **Test + rapport:** `python scripts/run_full_test.py --days 30 --report` of `python scripts/make_report.py`.
4. **Baseline (eenmalig of na release):** `python scripts/make_report.py --baseline`.
5. **Alleen bij groen + KPI’s ok:** commit + push. Op VPS: pull → `python scripts/make_report.py`.

### 3.2 Config aanpassen

- **Bestand:** `configs/xauusd.yaml` (en eventueel default.yaml).
- **Belangrijke velden:** `backtest.tp_r`, `sl_r`, `default_period_days`; `strategy.require_structure`, `structure_use_h1_gate`, `entry_require_sweep_displacement_fvg`, `entry_sweep_disp_fvg_min_count`; module-params (liquidity_sweep, displacement, fair_value_gaps, market_structure_shift).
- **Valideren:** `run_full_test.py --report` → vergelijk metrics met baseline; guardrails: geen slechtere max DD, PF niet onder minimum, geen >20% trade count stijging, winrate niet >2% daling.

### 3.3 Guardrails (geen change accepteren als)

- Max drawdown slechter dan baseline/drempel.
- Profit factor onder minimum (bijv. < 1.0).
- Regressietests falen (winrate >2% daling, trade count >20% stijging).
- Overtrading zonder verbetering expectancy/PF.

### 3.4 Waar wat staat (snel)

- **Strategie-logica:** `src/trader/strategies/sqe_xauusd.py`.
- **ICT-modules:** `src/trader/strategy_modules/ict/`.
- **Principes (canoniek):** `docs/OCLW_PRINCIPLES.md`.
- **Uitgebreide workflow (local vs VPS):** `docs/PROJECT_OVERVIEW_GPT.md`.
- **Totaal + ML-roadmap:** `docs/PROJECT_TOTAL.md`.
- **Backtest-loop en logs vergelijken:** `docs/OPENCLAW_BACKTEST_LOOP.md`.
- **Telegram:** `docs/TELEGRAM_COMMANDS.md`.
- **Log/artifacts-formaat:** `docs/ARTIFACTS_SCHEMA.md`.

---

## 4. Wat er in de loop der tijd is veranderd

- **Logging:** Naast .log is er **logs/json/run_<ts>.json** voor ML/verzameling; run_id, git_commit, kpis.
- **Artifacts:** Optioneel `artifacts/run_<ts>/` (metrics.json, report.md, equity.csv) voor Telegram en OpenClaw; `run_backtest_to_artifacts.py` en `run_backtest.sh --out`.
- **CLI:** `oclw_bot optimize` toegevoegd voor ML learning cycle.
- **Telegram:** `telegram_listener.py` voor RUN_BACKTEST met lock en timeout.
- **Strategie:** 3-pijler config met OR/AND; `require_structure`, `entry_require_sweep_displacement_fvg`, `entry_sweep_disp_fvg_min_count` in config; module-params (sweep_threshold_pct, min_body_pct, enz.) in xauusd.yaml.
- **Scripts:** `run_full_test.py` met --skip-fetch en --report; `setup_venv.py` voor één-klap setup; `deploy_check.sh` als gate.

---

## 5. Documentatie-index (actueel)

| Document | Inhoud |
|----------|--------|
| **docs/PROJECT_STATUS_GPT.md** | **Dit bestand** — fase, wat gebouwd, hoe werken. |
| **docs/PROJECT_OVERVIEW_GPT.md** | Helicopter view, local vs VPS, workflow, scripts, KPI’s. |
| **docs/PROJECT_TOTAL.md** | Totaal + VPS-besturing door OpenClaw + ML (huidig + roadmap). |
| **README.md** | Projectintro, structuur, quick start. |
| **RUN.md** | Setup, venv, fetch, CLI (backtest, fetch, optimize), tests, config. |
| **docs/OCLW_PRINCIPLES.md** | Canonieke regels (5 stappen, risk, sessies, wat nooit mag). |
| **docs/STRATEGY_BASIS.md** | 3 pijlers, mapping 5 stappen → code, roadmap. |
| **docs/ARCHITECTURE.md** | Data flow, uitbreiden (ICT, strategies, broker). |
| **docs/OPENCLAW_BACKTEST_LOOP.md** | Backtest runnen, logs vergelijken, config aanpassen, guardrails. |
| **docs/VPS_LOOP.md** | VPS runbook, scripts, rapportformaat, DoD, cron. |
| **docs/INSTRUCTIE_OPENCLAW_BOT.md** | OpenClaw op VPS: tests, rapport, waarden aanpassen, guardrails. |
| **docs/WERKWIJZE.md** | Test → rapport → vergelijken met baseline → beslissen → push. |
| **docs/SETTINGS.md** | Waar settings staan (YAML + code), hoe we ze bepalen. |
| **docs/ARTIFACTS_SCHEMA.md** | logs/, logs/json/, artifacts/ layout en formaat. |
| **docs/TELEGRAM_COMMANDS.md** | Telegram: RUN_BACKTEST, /help, setup. |
| **docs/TODO.md** | Open taken (MT5/Oanda, session filter, short SQE, enz.). |
| **oclw_bot/rules.md** | Regels voor Tester- en Improver-Agent. |

Als je dit bestand (en eventueel PROJECT_OVERVIEW_GPT.md) in GPT plakt, heeft het voldoende context om te weten waar het project staat en hoe er mee te werken.
