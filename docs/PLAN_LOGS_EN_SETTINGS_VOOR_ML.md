# Plan: Logs + instellingen bewaren voor ML-datasets

**Feb 2026.** Doel: bij elke run niet alleen de log en KPIs bewaren, maar ook de **gebruikte instellingen** (config-snapshot). Daarmee kunnen we datasets bouwen voor ML die trade settings vergelijken, ook over verschillende tijdspannen en timeframes.

---

## 1. Huidige situatie

- **Logs (mens):** `logs/oclw_bot_YYYY-MM-DD_HH-mm-ss.log` — blijft zoals nu.
- **Run-data (ML):** `logs/json/run_YYYY-MM-DD_HH-mm-ss.json` met o.a.:
  - `run_id`, `days`, `config` (alleen **pad**, bijv. `configs/xauusd.yaml`)
  - `kpis`: net_pnl, profit_factor, max_drawdown, winrate, trade_count, etc.
  - `tests`: passed/failed

**Probleem:** We slaan alleen het config-**pad** op. De daadwerkelijke waarden (tp_r, sl_r, strategy-params, timeframes, etc.) staan niet in de run-JSON. Voor ML die “welke settings presteren beter?” wil vergelijken, hebben we die waarden per run nodig.

---

## 2. Doel

1. **Instellingen per run bewaren** — bij elke run de **volledige gebruikte config** (na merge default + xauusd) als snapshot in de run-JSON (of een gekoppeld bestand) opslaan.
2. **Eén record per run** — één JSON per run met: context (run_id, days, timeframes, symbol) + **settings** (backtest, strategy, risk, …) + **kpis**.
3. **Datasets voor ML** — later kunnen we:
   - alle run-JSONs aggregeren tot één dataset (bijv. CSV/Parquet);
   - vergelijken: zelfde instellingen, andere periode; andere instellingen, zelfde periode; andere timeframes, zelfde instellingen.

---

## 3. Wat we per run bij moeten houden

### 3.1 Run-context (nu al grotendeels aanwezig)

| Veld        | Beschrijving                    | Voor ML |
|------------|----------------------------------|--------|
| `run_id`   | Unieke run (tijdstip)           | Id |
| `config_path` | Gebruikt configbestand       | Reproduceerbaarheid |
| `days`     | Backtest-periode (dagen)        | Feature / filter |
| `timeframes` | Uit config (bijv. `["15m","1h"]`) | Feature (later meerdere) |
| `symbol`   | Instrument (bijv. XAUUSD)       | Filter |

### 3.2 Settings-snapshot (nieuw)

Alles wat de uitkomst kan beïnvloeden, **na merge** (default + xauusd + env). Bijvoorbeeld:

- **backtest:** `default_period_days`, `tp_r`, `sl_r`, `session_filter`
- **risk:** `max_position_pct`, `max_daily_loss_r`
- **strategy:**  
  - vlaggen: `require_structure`, `structure_use_h1_gate`, `entry_require_sweep_displacement_fvg`  
  - getallen: `entry_sweep_disp_fvg_lookback_bars`, `entry_sweep_disp_fvg_min_count`  
  - per module: bv. `liquidity_sweep.*`, `displacement.*`, `fair_value_gaps.*`, `market_structure_shift.*`, `structure_context.*`

We slaan de **hele merged config** op (of een vast subset daarvan), zodat:
- we niets vergeten als we nieuwe parameters toevoegen;
- ML later kan flaten naar kolommen (bijv. `strategy.tp_r`, `strategy.liquidity_sweep.sweep_threshold_pct`).

### 3.3 KPIs (al aanwezig)

Blijft zoals nu: `net_pnl`, `profit_factor`, `max_drawdown`, `winrate`, `win_rate_pct`, `expectancy_r`, `trade_count`, `avg_holding_hours`.

---

## 4. Technische aanpassingen

### 4.1 Run-JSON uitbreiden

In **`scripts/run_full_test.py`** (functie `write_run_json`):

- Config laden met `load_config(args.config)` (zoals nu al voor backtest).
- In het payload dat we naar `logs/json/run_<ts>.json` schrijven:
  - **`config_path`** behouden (naast eventueel `config` voor backwards compatibility).
  - **`settings`** (of `config_snapshot`): het volledige merged config-dict, of een genormaliseerd subset:
    - `symbol`, `timeframes`
    - `backtest`, `risk`, `strategy`
  - Optioneel: **`timeframes`** en **`symbol`** ook top-level voor makkelijk filteren.

Belangrijk: geen gevoelige data (wachtwoorden, paden naar thuisdir) in de snapshot; alleen trading/strategy/backtest/risk. Eventueel een whitelist van keys (symbol, timeframes, backtest, risk, strategy) zodat we nooit per ongeluk env of paden meesturen.

### 4.2 Genormaliseerde “settings” voor ML

- **Optie A:** Hele merged config opslaan (eenvoudig, compleet). ML-pipeline flattent later geneste keys naar kolommen (bijv. `strategy.backtest.tp_r`).
- **Optie B:** Al bij schrijven een vast subset (symbol, timeframes, backtest, risk, strategy) in een object `settings` zetten. Zelfde info, iets schoner voor ML.

Aanbeveling: **Optie A** (hele config) met een vaste **whitelist van secties** (symbol, timeframes, backtest, risk, strategy, data alleen base_path/cache indien gewenst). Zo blijft één bron van waarheid en kunnen we later altijd extra velden toevoegen.

### 4.3 Schema run-JSON (na wijziging)

```json
{
  "run_id": "2026-02-09T20:09:18Z",
  "config_path": "configs/xauusd.yaml",
  "days": 30,
  "timeframes": ["15m", "1h"],
  "symbol": "XAUUSD",
  "report_run": false,
  "settings": {
    "backtest": { "default_period_days": 90, "tp_r": 1.5, "sl_r": 1.0, "session_filter": null },
    "risk": { "max_position_pct": 0.015, "max_daily_loss_r": 2.5 },
    "strategy": { ... }
  },
  "kpis": { "net_pnl": 58.15, "profit_factor": 1.28, ... },
  "tests": { "passed": 0, "failed": 0 }
}
```

(Eventueel `config` als alias voor `config_path` behouden voor backwards compatibility.)

---

## 5. Van run-JSONs naar ML-dataset

Later (aparte stap, geen vereiste voor “instellingen bewaren”):

1. **Verzameling:** Alle `logs/json/run_*.json` inlezen.
2. **Flatten:** Geneste `settings` naar kolommen (bijv. `settings.backtest.tp_r`, `settings.strategy.require_structure`). Run-context: `days`, `timeframes`, `symbol`, `run_id`.
3. **Targets:** KPIs als kolommen (net_pnl, profit_factor, winrate, max_drawdown, trade_count, etc.).
4. **Export:** Eén tabel (CSV of Parquet), één rij per run. Geschikt voor:
   - vergelijken:zelfde instellingen, andere tijdspannen;
   - vergelijken: andere instellingen,zelfde tijdspanne;
   - later: andere timeframes (bijv. 5m, 15m, 1h) met dezelfde of andere instellingen.

Script **`scripts/build_ml_dataset.py`** (geïmplementeerd):
- leest `logs/json/run_*.json`;
- flattent `settings` naar kolommen (prefix `setting_*`);
- voegt run-context (run_id, days, timeframes, symbol, config_path) en kpis (prefix `kpi_*`) toe;
- schrijft één rij per run naar **`data/ml/runs.csv`**; optioneel **`data/ml/runs.parquet`** met `--parquet`.

Gebruik: `python scripts/build_ml_dataset.py` of `python scripts/build_ml_dataset.py --parquet`.

---

## 6. Tijdspannen en timeframes (later)

- **Zelfde instellingen, andere tijdspannen:** Nu al mogelijk zodra we `days` en `settings` per run hebben: filter op gelijke `settings`-hash of key-set, vergelijk `days` 30 vs 60 vs 90 en bijbehorende KPIs.
- **Zelfde tijdspanne, andere instellingen:** Filter op `days` (en eventueel `symbol`), vergelijk verschillende `settings` en KPIs.
- **Andere timeframes:** Zodra we backtest ondersteunen voor meerdere timeframes (of aparte runs per timeframe), komt `timeframes` in elk run-record. Dan: filter op timeframe(s), vergelijk instellingen en KPIs over die timeframe.

Alles wat we nu in de run-JSON zetten (run_id, days, timeframes, symbol, settings, kpis) is daarop voorbereid.

---

## 7. Samenvatting acties

| # | Actie | Prioriteit |
|---|--------|------------|
| 1 | Run-JSON uitbreiden: bij elke run merged config (of whitelist) als `settings` + `timeframes` en `symbol` top-level opslaan | Hoog |
| 2 | ARTIFACTS_SCHEMA.md bijwerken: `logs/json/run_<ts>.json` beschrijven met velden `settings`, `timeframes`, `symbol` | Medium |
| 3 | Script `scripts/build_ml_dataset.py`: alle run-JSONs → één geflatte dataset (CSV/Parquet) voor ML | **Gereed** |

Daarna: logs blijven we bewaren zoals nu; instellingen zitten per run in dezelfde run-JSON, zodat we daar direct datasets voor ML uit kunnen maken en trade settings over tijdspannen en timeframes kunnen vergelijken.
