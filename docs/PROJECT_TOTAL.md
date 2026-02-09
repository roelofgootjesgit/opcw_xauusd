# oclw_xauusd — Totaal projectoverzicht

Eén document met: wat het project is, hoe de VPS door OpenClaw wordt bestuurd, en wat we (gaan) bouwen op het gebied van ML.

---

## 1. Wat is dit project?

**oclw_bot** (repo: opclw_xauusd) is een **ICT-style backtesting- en execution-framework** voor XAUUSD (goud), uitbreidbaar naar andere symbolen.

- **Data:** Parquet in `data/market_cache/SYMBOL/`; fetch via Yahoo Finance (GC=F) of eigen data.
- **Strategie:** SQE-style (liquidity sweep + displacement + FVG ± market structure shift), gebouwd uit modulaire ICT-modules (sweep, FVG, order blocks, breaker blocks, imbalance zones, MSS).
- **Pipeline:** Config (YAML + .env) → load data → indicators (ATR, EMA, swings) → strategy modules → entries → backtest (TP/SL in R) → metrics & report.
- **Tech:** Python 3.10+, CLI `oclw_bot` (backtest, fetch), tests (unit, integration, regression, performance).

**Belangrijke mappen:**

| Map | Doel |
|-----|------|
| `configs/` | default.yaml, xauusd.yaml — symbol, timeframes, backtest/risk/strategy params |
| `src/trader/` | app, config, backtest, strategies, strategy_modules/ict, execution, indicators, io, **ml/** |
| `data/` | market_cache (Parquet), signals |
| `tests/` | unit, integration, regression, performance, smoke |
| `reports/latest/` | REPORT.md, metrics.json (per run) |
| `reports/history/` | baseline.json (gouden KPI-referentie) |
| `scripts/` | run_tests.sh, run_backtest.sh, make_report.py |
| `oclw_bot/` | rules.md, prompts (tester.md, improver.md) — **VPS-agents** |
| `docs/` | ARCHITECTURE, VPS_LOOP, TODO, INSTRUCTIE_OPENCLAW_BOT, PROJECT_OVERVIEW_GPT, **PROJECT_TOTAL** (dit bestand) |

---

## 2. Local vs VPS (kort)

- **Lokaal:** ontwikkelen, `oclw_bot fetch`, tests + backtest + `make_report.py`; alleen bij groen + KPI’s ok **pushen**.
- **VPS:** `git pull` → data aanwezig → `make_report.py` (cron/systemd); **OpenClaw-agents** (Tester, Improver) sturen de loop: rapport lezen, kleine fixes/parameters, alleen accepteren binnen guardrails.
- **.env** en **baseline:** lokaal en VPS elk eigen .env; baseline is de referentie voor regressie (vaak op VPS/gedeeld gezet).

Zie **docs/PROJECT_OVERVIEW_GPT.md** voor de uitgebreide tabel en workflow (lokaal testen → dan pas VPS).

---

## 3. Besturing van de VPS door OpenClaw

OpenClaw is de **bot/agent-laag** die op de VPS de “Test → Rapport → Verbeter”-loop uitvoert. De bot **bestuurt** de VPS in de zin van: **welke commando’s wanneer draaien** en **welke wijzigingen (code/parameters) worden geaccepteerd of teruggedraaid**.

### 3.1 Rollen: Tester-Agent en Improver-Agent

| Agent | Verantwoordelijkheid | Mag niet |
|-------|----------------------|----------|
| **Tester-Agent** | Tests uitbreiden, tests runnen, rapport genereren (`make_report.py`). | Geen strategie- of parameterwijzigingen. |
| **Improver-Agent** | Rapport lezen, root-cause analyse, **kleine fixes/parameter-aanpassingen** voorstellen en doorvoeren, opnieuw testen. | Geen grote refactors; alleen mergen als tests groen en KPI’s binnen guardrails. |

Beide volgen **oclw_bot/rules.md**. Prompts: `oclw_bot/prompts/tester.md`, `oclw_bot/prompts/improver.md`.

### 3.2 Hoe “bestuurt” OpenClaw de VPS?

1. **Scripts aansturen**
   - Op de VPS worden door cron of systemd periodiek (of na push) uitgevoerd:
     - `./scripts/run_tests.sh` of `python -m pytest tests/ -v --tb=short`
     - `./scripts/run_backtest.sh` (optioneel)
     - **`python scripts/make_report.py`** → vult `reports/latest/REPORT.md` en `reports/latest/metrics.json`
   - De **agents** (als ze op de VPS of in een runner draaien) **lezen** dit rapport en **nemen beslissingen**: wijziging behouden of rollback.

2. **Beslissingsregels (guardrails)**
   - **Geen change accepteren** als:
     - Max drawdown slechter dan baseline/drempel
     - Profit factor onder minimum (bijv. < 1.0 of onder baseline)
     - Regressietests falen (bijv. winrate >2% daling, trade count >20% stijging)
     - Overtrading zonder verbetering van expectancy/PF
   - **Alleen accepteren** als alle tests groen zijn en KPI’s binnen de afgesproken marges.

3. **Parameter-aanpassingen**
   - Improver past **max 1–3 parameters** per iteratie aan (bijv. in `configs/xauusd.yaml`: tp_r, sl_r, risk, strategy-params).
   - Geen strategy rewrite zonder regressietest; geen parameter drift zonder duidelijke KPI-winst; geen verbetering op te korte data-periode (overfit).

4. **Automatisering (VPS)**
   - **Cron:** bijv. dagelijks `cd /pad/naar/opclw_xauusd && python scripts/make_report.py` → log naar `/var/log/opclaw/`.
   - **Systemd (optie):** service die een runner-script periodiek laat draaien (tests + report).
   - Na **git push**: op VPS `git pull` → daarna `make_report.py`; agents bepalen of de wijziging blijft of wordt teruggedraaid.

Samengevat: OpenClaw **bestuurt** de VPS door (1) de juiste scripts te laten draaien, (2) het rapport te laten genereren, en (3) via Tester/Improver alleen wijzigingen te **accepteren** die voldoen aan de regels in **oclw_bot/rules.md**. Zie ook **docs/INSTRUCTIE_OPENCLAW_BOT.md** en **docs/VPS_LOOP.md**.

---

## 4. ML: wat er is en wat we gaan maken

### 4.1 Wat er al is (ML-stack in `src/trader/ml/`)

| Onderdeel | Doel |
|-----------|------|
| **config_space.py** | Probabilistisch configuratie-ruimte voor strategy/backtest (uniform, normal, loguniform, choice). `get_default_config_space()` voor SQE-parameters (tp_r, sl_r, lookback, sweep_threshold, displacement, FVG, MSS, use_mss). `sample_config()` voor sampling; `config_to_backtest_cfg()` om sample naar backtest-config te maken. |
| **rewards.py** | Multi-objective reward/fitness: net_pnl (R), profit_factor, drawdown resistance, win_rate. Standaardgewichten: 0.4, 0.3, 0.2, 0.1. `calculate_reward(metrics)` / `calculate_reward_from_trades(trades)`. |
| **strategy_optimizer.py** | **StrategyOptimizer**: Thompson-Sampling-achtige optimalisatie. Genereert candidate configs (exploit: perturb rond best-so-far; explore: sample uit config space), evalueert via backtest, houdt best config en reward bij. `generate_candidate_config()`, `evaluate_config()`, `update_strategy()`, `get_best_config()`. |
| **knowledge_base.py** | **StrategyKnowledgeBase**: genealogie van configs, regime-labels (optioneel), opslag van succesvolle configs voor transfer learning. `record_evaluation()`, succesvolle configs gesorteerd op reward, max N bewaren. |
| **continuous_learning.py** | **ContinuousLearningAgent**: één leercyclus = (1) data ophalen (MarketDataCollector → ensure_data/Parquet), (2) N candidate configs genereren en evalueren, (3) optimizer + knowledge base updaten, (4) best config persisteren naar `reports/latest/best_ml_config.json`. **MarketDataCollector**: fetch_latest_data() voor symbol/timeframe/period_days. |
| **features/** | **FeatureExtractionPipeline**: market_structure → liquidity → technical → statistical. Modules: market_structure, liquidity, technical, statistical. Output: kolommen met prefix `feat_*` voor toekomstige ML-modellen (bijv. regime-classificatie of entry-scoring). |

Deze ML-stack is **nu vooral gericht op hyperparameter-optimalisatie** (config space + reward + backtest) en **feature-extractie**; de continuous-learning loop kan lokaal of op de VPS worden gedraaid maar is nog niet geïntegreerd in de OpenClaw Tester/Improver-flow.

### 4.2 Wat we gaan maken (ML-roadmap)

- **Integratie ML met VPS-loop**
  - Continuous-learning cyclus (bijv. wekelijks) op de VPS: data ophalen → candidate configs evalueren → best config opslaan; Improver mag deze best config als voorstel gebruiken (nog steeds binnen guardrails en max 1–3 changes).
  - Optioneel: `make_report.py` uitbreiden met een “ML run”-modus die na de gewone backtest een korte learning cycle draait en `best_ml_config.json` bijwerkt.

- **Regime-detectie en regime-specifieke configs**
  - Gebruik van **features** (market_structure, liquidity, volatility) om marktregime te taggen (bijv. trending / ranging / volatile).
  - **Knowledge base** uitbreiden: succesvolle configs per regime; bij inference regime schatten en beste config voor dat regime kiezen (transfer learning).

- **Entry-scoring / filter met ML**
  - Feature pipeline al beschikbaar; volgende stap: een lichtgewicht model (bijv. classifier of regressie op “win probability” of “expected R”) dat op `feat_*` traint en entries filtert of weegt in de backtest/execution.

- **Betere optimalisatie en veiligheid**
  - Bayesian/optuna-achtige search naast Thompson-style (optioneel); constraint dat alleen configs die binnen guardrails vallen (max DD, PF, winrate, trade count) worden geaccepteerd in de knowledge base en voor deployment.
  - Baseline en regressietests blijven leidend: ML mag geen slechtere KPI’s opleveren dan de baseline.

- **Broker en live/paper (TODO)**
  - MT5/Oanda connector achter `broker_stub` (zie docs/TODO.md); daarna kan ML ook voor paper/live gebruikt worden (zelfde config space + reward, andere execution path).

Dit is de richting: **bestaande ML (config space, optimizer, rewards, knowledge base, continuous learning, features) uitbouwen naar VPS-gestuurde loop, regime-awareness en entry-ML**, met guardrails en baseline centraal.

---

## 5. Documentatie-index

| Document | Inhoud |
|----------|--------|
| **README.md** | Projectintro, structuur, quick start, VPS-loop in het kort. |
| **RUN.md** | Setup, venv, Yahoo/fetch, CLI (backtest, fetch), tests, config. |
| **docs/ARCHITECTURE.md** | Data flow, uitbreiden (ICT-modules, strategies, broker). |
| **docs/VPS_LOOP.md** | VPS runbook, scripts, rapportformaat, DoD. |
| **docs/INSTRUCTIE_OPENCLAW_BOT.md** | OpenClaw op de VPS: tests, rapport, waarden aanpassen, guardrails, automatisering. |
| **docs/TODO.md** | Open taken (MT5/Oanda, session filter, short SQE, HTML/PDF report, extra tests). |
| **docs/PROJECT_OVERVIEW_GPT.md** | Helicopter view + local vs VPS voor gebruik in GPT. |
| **docs/PROJECT_TOTAL.md** | **Dit document:** totaaloverzicht, VPS-besturing door OpenClaw, ML (huidig + roadmap). |
| **oclw_bot/rules.md** | Regels voor Tester- en Improver-Agent. |
| **oclw_bot/prompts/tester.md** | Tester-Agent prompt. |
| **oclw_bot/prompts/improver.md** | Improver-Agent prompt. |

---

## 6. Snelle referentie: belangrijke commando’s

```bash
# Setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[yfinance]"
cp .env.example .env

# Data
oclw_bot fetch
oclw_bot fetch --days 90

# Run
oclw_bot backtest --config configs/xauusd.yaml
pytest tests/ -v --tb=short
python scripts/make_report.py
python scripts/make_report.py --baseline

# VPS (na pull)
python scripts/make_report.py
```

Met dit document heb je één plek voor het totale plaatje: project, VPS-besturing door OpenClaw, en wat er is en komt op het gebied van ML.
