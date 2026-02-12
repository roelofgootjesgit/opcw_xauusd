# OpenClaw: Backtest runnen en aanpassen voor betere uitkomst

**Feb 2026.** Voor overzicht scripts en fase → **docs/PROJECT_STATUS_GPT.md**.

Korte instructie voor de bot: hoe backtest draaien, logs vergelijken en config/strategie stapsgewijs verbeteren.

---

## 1. Backtest runnen

**Aanbevolen (fetch + backtest in één):**
```bash
cd opclw_xauusd
.\.venv\Scripts\Activate.ps1   # Windows; Linux: source .venv/bin/activate
python scripts/run_full_test.py --days 30 --config configs/xauusd.yaml
```

**Alleen backtest** (bestaande data):
```bash
oclw_bot backtest --config configs/xauusd.yaml
# of: python -m src.trader.app backtest --config configs/xauusd.yaml
```

**Volledig rapport** (tests + backtest + REPORT.md + metrics.json):
```bash
python scripts/run_full_test.py --days 30 --report
# of: python scripts/make_report.py
```

Elke run schrijft:
- **Log (mens):** `logs/oclw_bot_YYYY-MM-DD_HH-mm-ss.log`
- **Log (ML):** `logs/json/run_YYYY-MM-DD_HH-mm-ss.json`

---

## 2. Logs vergelijken

### In het .log-bestand zoeken naar:

**Eén regel per run (samenvatting):**
```
Backtest result: net_pnl=... profit_factor=... winrate=...% max_dd=...R trade_count=...
```

**Per trade:**
```
Trade #N | entry ... @ price | exit ... @ price | sl=... tp=... | WIN/LOSS | pnl_usd=... pnl_r=...
```

**Belangrijke KPIs om runs te vergelijken:**

| KPI | Beter als |
|-----|-----------|
| **net_pnl** | Hoger (positief = winst) |
| **profit_factor** | > 1.0 en hoger |
| **winrate** | Hoger % (maar niet ten koste van PF) |
| **max_dd** | Minder negatief (bijv. -4.00R beter dan -8.00R) |
| **trade_count** | Voldoende (niet 0), maar geen explosie (regressie: max ~20% meer dan baseline) |

### Voorbeeld vergelijking (uit echte logs)

| Log (run) | trade_count | net_pnl | winrate | max_dd | Opmerking |
|-----------|-------------|---------|---------|--------|-----------|
| 21-47-23 | 0 | — | — | — | **Slecht:** geen trades → strategie te streng of data/period mismatch |
| 21-38-59 | 13 | -41.53 | 46.2% | -4.00R | Meer selectief, minder trades, nog verlies |
| 21-31-56 | 41 | -50.21 | 43.9% | -8.00R | Meer trades, dieper drawdown |

Conclusie: 0 trades = ontspan filters in config; te veel verliezen = strenger entry (bijv. `require_structure`, session filter) of betere TP/SL-balans.

---

## 3. Aanpassen voor betere uitkomst

### Config (geen code): `configs/xauusd.yaml`

- **Geen/weinig trades (0–5):**  
  - `strategy.entry_sweep_disp_fvg_min_count`: 2 → 1 (soepeler).  
  - `strategy.require_structure`: true → false (meer trades, vaak slechtere kwaliteit).  
  - `strategy.liquidity_sweep.sweep_threshold_pct` of `displacement.min_move_pct` iets verlagen.  
  - `strategy.entry_require_sweep_displacement_fvg`: true → false (alleen als je bewust meer signalen wilt).

- **Te veel verliezen / lage winrate / slechte PF:**  
  - `strategy.require_structure`: false → true.  
  - `strategy.structure_use_h1_gate`: false → true (strenger).  
  - `backtest.tp_r` / `backtest.sl_r` aanpassen (bijv. tp_r 1.5 → 1.8 voor grotere wins).  
  - Modules aanscherpen: hoger `min_body_pct`, `min_move_pct`, `min_gap_pct`.

- **Te grote drawdown:**  
  - Strakkere entries (require_structure, H1 gate), of kleinere positie (risk in config).

### Code (strategie)

- **Signaalgeneratie:** `src/trader/strategies/sqe_xauusd.py`  
- **ICT-modules (sweep, FVG, displacement, structure):** `src/trader/strategy_modules/ict/`  
Aanpassingen hier: kleine stappen doen, daarna direct backtest opnieuw draaien en **logs vergelijken**.

### Guardrails (regressie)

- Winrate niet >2% laten dalen t.o.v. baseline.  
- Trade count niet >20% laten stijgen t.o.v. baseline.  
- Max drawdown en profit factor niet bewust verslechteren.

Baseline: `reports/history/baseline.json` (na `make_report.py --baseline`).

---

## 4. Automatische optimalisatie: `auto_improve.py`

**Nieuw (feb 2026):** het hele proces is nu geautomatiseerd. Eén commando doet de volledige loop:

```bash
# Rule-based (geen API credits nodig):
python scripts/auto_improve.py --max-iter 3 --days 30

# Met OpenClaw/Claude (Anthropic credits nodig):
python scripts/auto_improve.py --max-iter 3 --days 30 --use-llm
```

### Wat het script doet per iteratie:

1. `run_full_test.py` (fetch + backtest + tests + rapport + llm_input.json)
2. Leest `reports/latest/llm_input.json`
3. Besluit: ACCEPT / PROPOSE_CHANGE / STOP / REJECT
4. Past config aan via `apply_changes.py` + re-run
5. Herhaalt tot ACCEPT, STOP, of max iteraties

### Drie decider-modi:

| Modus | Flag | Credits nodig | Kwaliteit |
|-------|------|--------------|-----------|
| **Rule-based** | (default) | Nee | 90% — volgt AGENTS.md heuristieken |
| **LLM (OpenClaw)** | `--use-llm` | Ja (Anthropic) | 100% — kan patronen herkennen, creatievere combinaties |
| **ML (toekomst)** | `--use-ml` | Nee | Thompson Sampling op historische performance data |

### Alle opties:

| Flag | Wat het doet |
|------|-------------|
| `--max-iter 5` | Max 5 iteraties (default: 1) |
| `--days 30` | Backtest periode (default: 30) |
| `--config` | Config YAML (default: configs/xauusd.yaml) |
| `--dry-run` | Laat beslissingen zien zonder toe te passen |
| `--skip-first-test` | Gebruik bestaande llm_input.json |
| `--use-llm` | OpenClaw/Anthropic i.p.v. regels |
| `--llm-agent main` | OpenClaw agent id (default: main) |

### Voorbeeld output:

```
auto_improve - INFO - ITERATION 1/3
auto_improve - INFO - KPIs: PF=0.82 WR=35.3% DD=-7.0R trades=17 | Flags: PF_BELOW_1
auto_improve - INFO - Decision: PROPOSE_CHANGE | Reasons: ['PF_BELOW_1'] | Changes: 2
auto_improve - INFO -   Change: backtest.tp_r: 1.5 -> 2.0
auto_improve - INFO -   Change: strategy.structure_use_h1_gate: false -> true
...
auto_improve - INFO - ITERATION 3/3
auto_improve - INFO - KPIs: PF=1.25 WR=33.3% DD=-4.0R trades=12 | Flags: none
auto_improve - INFO - Decision: ACCEPT | Reasons: ['ALL_GREEN'] | Changes: 0
auto_improve - INFO - Loop finished: ACCEPT
```

---

## 5. Handmatige loop (als alternatief)

1. **Run:** `python scripts/run_full_test.py --days 30 --config configs/xauusd.yaml --report`
2. **Lees:** `cat reports/latest/llm_input.json`
3. **Besluit:** maak `decision.json` (handmatig of via Claude)
4. **Pas toe:** `python scripts/apply_changes.py decision.json --config configs/xauusd.yaml --re-run`
5. **Herhaal** vanaf stap 1.

---

## 6. ML Roadmap

Het systeem is opgezet als een **pluggable architecture** met een `Decider` interface:

```
Decider (Protocol)
├── RuleBasedDecider  ← huidige default (deterministische heuristieken)
├── LLMDecider        ← OpenClaw/Anthropic (--use-llm)
└── MLDecider         ← toekomst: Thompson Sampling + historische data
```

### Geplande ML-uitbreidingen:

1. **MLDecider met Thompson Sampling** — gebruikt `src/trader/ml/strategy_optimizer.py`
   - Leert van historische run-data in `logs/json/run_*.json`
   - Kiest parameters op basis van welke combinaties eerder het beste werkten
   - Beter dan rule-based bij complexe interacties tussen parameters

2. **Feature-gebaseerde beslissingen** — gebruikt `src/trader/ml/features/pipeline.py`
   - Marktregime-detectie (trending vs ranging)
   - Volatiliteits-aanpassingen (hogere tp_r bij hogere volatiliteit)
   - Seizoenspatronen (dag van de week, sessie)

3. **Meta-learning** — gebruikt `src/trader/ml/knowledge_base.py`
   - Configs opslaan als "genealogie" (welke config kwam voort uit welke)
   - Regime-tagging (welke config werkt in welk marktregime)
   - Cross-timeframe learning

### Data die al verzameld wordt:

- `logs/json/run_*.json` — KPIs + settings per run
- `logs/json/decision_*.json` — elke beslissing met reason_codes
- `logs/json/auto_improve_*.json` — resultaat per optimizer-sessie
- `reports/history/baseline.json` — referentiepunt

Deze data vormt de training set voor de MLDecider.

Voor volledige instructie en VPS: zie `docs/INSTRUCTIE_OPENCLAW_BOT.md`.
