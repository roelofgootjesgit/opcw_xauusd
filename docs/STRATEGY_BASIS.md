# SQE XAUUSD – Strategie basis

**Feb 2026.** Voor huidige fase en config-overzicht → **docs/PROJECT_STATUS_GPT.md**.

**Canonieke regels:** `docs/OCLW_PRINCIPLES.md` (Meten → Wachten → Reageren; geen voorspellen/gokken).

De strategie volgt de **5 stappen** uit de principes; de huidige code implementeert dit via **3 pijlers** (trend → liquiditeit/levels → entry trigger).

---

## Mapping: 5 stappen → code

| Stap (OCLW_PRINCIPLES) | Huidige implementatie | Status |
|------------------------|------------------------|--------|
| **1. Marktstructuur (HTF→LTF)** | MSS + displacement op 1 TF (M15) | ⚠️ Geen H1/M15/M5-scheiding; geen BULLISH/BEARISH/RANGE-label |
| **2. Liquiditeit detecteren** | Liquidity sweep (swing high/low) + FVG | ⚠️ Geen equal highs/lows, PDH/PDL, Asia/London; geen `liquidity_above/below` output |
| **3. Sweep verplicht** | `liquidity_sweep` + MSS in entry-voorwaarden | ✅ Sweep + structure break vereist (via 3 pijlers) |
| **4. Entry-validatie** | FVG, displacement (OB/breaker in modules, niet in entry AND) | ✅ FVG + displacement; OB/breaker optioneel uitbreidbaar |
| **5. Risk model** | ATR-based SL/TP (1R/2R) | ⚠️ SL nog niet expliciet “boven/onder sweep”; geen TP3 = tegenoverliggende liquiditeit |

---

## 3 pijlers (zoals nu in code)

Entry = **alle drie** tegelijk:

1. **Trend context** — structure + momentum (MSS en/of displacement).
2. **Liquiditeit / levels** — sweep + FVG (waar ligt het geld, waar is level).
3. **Entry timing (trigger)** — bv. displacement-candle of sweep-candle.

Harde regels uit principes blijven: **RANGE = NO TRADE**; alleen long bij bullish structure, alleen short bij bearish; **geen entry zonder sweep**.

---

## Config (3 pijlers)

- **trend_context:** `modules: [market_structure_shift, displacement]`, `require_all: false` (OR).
- **liquidity_levels:** `modules: [liquidity_sweep, fair_value_gaps]`, `require_all: true` (AND).
- **entry_trigger:** `module: displacement` (of `liquidity_sweep`, `market_structure_shift`).
- **require_structure:** alleen entries in expliciete structuur (HH/HL voor long, LH/LL voor short); **RANGE geblokkeerd** → minder contextloze trades, betere PnL/DD. Zie `structure_context` (lookback, pivot_bars).

Module-params: zie `configs/xauusd.yaml` (liquidity_sweep, displacement, fair_value_gaps, market_structure_shift, structure_context).

---

## Waar de code staat

| Onderdeel | Pad |
|-----------|-----|
| 3-pijler logica | `src/trader/strategies/sqe_xauusd.py` |
| ICT-modules | `src/trader/strategy_modules/ict/` |
| Backtest (SL/TP) | `src/trader/backtest/engine.py` |
| Config | `configs/xauusd.yaml` (strategy) |

---

## Roadmap (richting volledige principes)

- **Structuur-labels:** BULLISH_STRUCTURE / BEARISH_STRUCTURE / RANGE per timeframe; RANGE → NO TRADE.
- **HTF/LTF:** H1 context, M15 execution, M5 optioneel; nooit tegen H1 in.
- **Liquiditeit-output:** Equal highs/lows, PDH/PDL, Asia/London; formaat `liquidity_above`, `liquidity_below`, `probable_target`.
- **Risk:** SL altijd boven/onder sweep-high/low; TP3 = tegenoverliggende liquiditeit.
- **Sessies:** Alleen London + NY entries; Asia alleen range-detectie; news-filter (CPI/FOMC).
- **Trade management:** Max 1–2 trades per sessie; geen stacking; geen re-entry zonder nieuwe sweep.

ML alleen: configs ranken, regime labelen, entries filteren — nooit forceren (zie `oclw_bot/rules.md`).
