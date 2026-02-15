# Hoe we de settings bepalen

**Feb 2026.** Voor huidige fase → **docs/PROJECT_STATUS_GPT.md**.

Eén idee: **alle instellingen op één plek, bepalen door meten (backtest + guardrails), nooit door gok of ML-override.**

---

## 1. Waar staan de settings?

| Laag | Bestand | Wat |
|------|---------|-----|
| **Basis** | `configs/default.yaml` | symbol, timeframes, data path, backtest (tp_r, sl_r, period_days), risk, logging |
| **Instrument** | `configs/xauusd.yaml` | Overrides voor XAUUSD: risk, backtest period, **strategy** (3 pijlers + module-params) |
| **Code-defaults** | `src/trader/strategies/sqe_xauusd.py` | 3 pijlers (trend/liquidity/trigger) + module-params als YAML niets zegt |

**Regel:** Alles wat je wilt aanpassen doe je in **YAML** (default of xauusd). Code-defaults zijn alleen fallback; de “bron van waarheid” voor een run is: `default.yaml` ← merge ← `xauusd.yaml` (en eventueel `.env` voor paden).

---

## 2. Overzicht settings (wat er is)

### Backtest
- `default_period_days` — periode (dagen) voor backtest
- `tp_r` — take profit in R (t.o.v. ATR-SL). **Huidig: 2.5** (mechanisch onderbouwd via MFE-klif)
- `sl_r` — stop loss in ATR-multiples. **Huidig: 1.0** (minimaal levensvatbaar, winners MAE tot 0.97R)
- `session_filter` — `null` (killzones te smal voor huidige entry-logica; getest en gerevert)

### Regime profiles
- `regime_profiles` — **`null` (uitgeschakeld, feb 2026)**. Was trending/ranging/volatile
  TP/SL modulatie. Bleek schadelijk: ranging sl_r=0.8 doodde winners, volatile R:R=1.33
  degradeerde expectancy. Flat tp/sl is significant beter (PF 1.13→1.75, DD -7R→-4R).
  Rollback-instructies staan als comment in `configs/xauusd.yaml`.
  Zie `docs/BASELINE_OPTIMIZATION_LOG.md` iteratie 9-10 voor volledig bewijs.

### Risk
- `max_position_pct` — max positiegrootte (% kapitaal)
- `max_daily_loss_r` — max dagverlies in R

### Strategy (3 pijlers)
- `trend_context.modules` — bv. `[market_structure_shift, displacement]`
- `trend_context.require_all` — `false` = OR, `true` = AND
- `liquidity_levels.modules` — bv. `[liquidity_sweep, fair_value_gaps]`
- `liquidity_levels.require_all` — meestal `true` (sweep + FVG)
- `entry_trigger.module` — `displacement` | `liquidity_sweep` | `market_structure_shift`

### Module-params (ICT)
- **liquidity_sweep:** `lookback_candles`, `sweep_threshold_pct`, `reversal_candles`
- **displacement:** `min_body_pct`, `min_candles`, `min_move_pct`
- **fair_value_gaps:** `min_gap_pct`, `validity_candles`
- **market_structure_shift:** `swing_lookback`, `break_threshold_pct`

(Zie `configs/xauusd.yaml` en `sqe_xauusd.py` → `DEFAULT_MODULE_CONFIG` voor exacte default-waarden.)

---

## 3. Hoe bepalen we de waarden?

- **Niet:** voorspellen, gokken, of ML die regels override.
- **Wel:**
  1. **Backtest** — run op vaste periode (bijv. 30/60/90 dagen),zelfde data.
  2. **Baseline** — eerste “goede” run vastleggen in `reports/history/baseline.json` (KPI’s).
  3. **Guardrails** — een wijziging in settings accepteren alleen als:
     - regressietests groen blijven,
     - max DD niet slechter,
     - profit factor niet onder minimum,
     - geen overtrading (geen grote stijging trade count zonder verbetering expectancy).
  4. **Optioneel:** ML mag **configs ranken** of kandidaten voorstellen; wij accepteren alleen na bovenstaande checks (geen automatische override).

Concreet: je past iets aan in `configs/xauusd.yaml` (of default), draait `python scripts/run_full_test.py --report`, kijkt naar rapport + metrics, vergelijkt met baseline. Alleen als het binnen de regels valt, wordt die setting de nieuwe standaard.

---

## 4. Wie beslist?

- **Lokaal / human:** jij past YAML aan, run full test, beslist of je de wijziging houdt of terugdraait.
- **VPS / Improver-agent:** stelt alleen wijzigingen voor die binnen guardrails vallen; geen merge zonder groene tests + KPI-check (zie `oclw_bot/rules.md`).

Geen systeem of ML “beslist” de settings; die worden **gevalideerd** door backtest + baseline + guardrails.

---

## 5. Snelle referentie

- **Default strategy- en module-waarden:** `src/trader/strategies/sqe_xauusd.py` → `get_sqe_default_config()` en `DEFAULT_MODULE_CONFIG`.
- **Waar je overrides zet:** `configs/xauusd.yaml` onder `strategy:` (en evt. `backtest:`, `risk:`).
- **Valideren:** `python scripts/run_full_test.py --report` → `reports/latest/REPORT.md` en `metrics.json`; vergelijk met `reports/history/baseline.json`.

Daarmee is het idee duidelijk: **settings = YAML + code-defaults; bepalen = backtest + baseline + guardrails; niemand “gokt” ze, ML mag alleen ranken/filteren.**
