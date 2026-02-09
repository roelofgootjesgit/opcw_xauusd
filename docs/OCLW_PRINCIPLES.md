# oclw — Principes & Regels (canoniek)

**Project:** oclw / XAUUSD  
**Rol:** Deterministische ICT-style execution bot  
**Principe:** Meten → Wachten → Reageren  
**Verboden:** voorspellen, gokken, compenseren  

---

## 1. Wat oclw WEL doet (kernopdracht)

oclw denkt niet en voorspelt niet.

De bot mag **uitsluitend**:

- **Marktstructuur classificeren**
- **Liquiditeit lokaliseren**
- **Reactie op manipulatie traden**

**Alles daarbuiten = NO TRADE**

---

## 2. Stap 1 — Marktstructuur lezen (HTF → LTF)

### Timeframes

| TF  | Rol |
|-----|-----|
| **H1** | context |
| **M15** | execution bias |
| **M5**  | entry validatie (optioneel) |

oclw moet per timeframe bepalen:

- Laatste structure break
- HH / HL / LH / LL
- Laatste pullback zone
- **Structuur-labels (exact één):** `BULLISH_STRUCTURE` | `BEARISH_STRUCTURE` | `RANGE`

### Harde regels

| Regel |
|-------|
| RANGE → **NO TRADE** |
| Alleen **LONGS** bij BULLISH_STRUCTURE |
| Alleen **SHORTS** bij BEARISH_STRUCTURE |
| **Nooit** tegen H1-structuur in |

---

## 3. Stap 2 — Liquiditeit detecteren (waar ligt het geld?)

oclw moet automatisch markeren:

**Liquidity Objects**

- Equal Highs / Equal Lows
- Previous Day High / Low
- Asia High / Low
- London High / Low

**Output (verplicht):**

```json
{
  "liquidity_above": [...],
  "liquidity_below": [...],
  "probable_target": "above" | "below"
}
```

---

## 4. Stap 3 — Liquidity Sweep is verplicht

oclw mag **pas verder** als:

1. **Liquiditeit is gesweept**
2. **Daarna** een structure break in de tegenovergestelde richting optreedt

**Voorbeeld SHORT-flow:**

- Equal highs / PDH wordt gepakt  
- Bearish displacement candle  
- Bearish MSS op M5/M15  
- **Pas dan** mag entry-logica actief worden  

**Geen sweep = NO TRADE**

---

## 5. Stap 4 — Entry-validatie (bewijs, geen gevoel)

Na **sweep + MSS** moet **minstens één** van de volgende aanwezig zijn:

- Fair Value Gap (FVG)
- Order Block
- Breaker Block
- Displacement candle

**Canonieke entry-logica (voorbeeld SHORT):**

```
IF liquidity_swept == TRUE
AND structure_shift == BEARISH
AND displacement_detected == TRUE
THEN
  wait for retrace into imbalance / OB
  enter short
  stop above sweep high
```

---

## 6. Stap 5 — Risk Model (heilig)

oclw **MOET** altijd:

- **Stop loss:** boven / onder sweep-high of sweep-low
- **TP1:** 1R
- **TP2:** 2R
- **TP3:** tegenoverliggende liquiditeit

**Trade management**

- Max **1–2 trades per sessie**
- Geen stacking
- Geen her-entry zonder **nieuwe** sweep

---

## 7. Sessies & filters

### Actieve sessies

- London
- New York

### Verboden

- **Azië** — alleen range-detectie, geen entries
- **CPI / FOMC / high-impact news**
- **Volatiliteit zonder sweep**

---

## 8. Wat oclw NOOIT mag doen

- Entries in consolidatie
- Entries zonder liquidity sweep
- Tegen hogere timeframe structuur
- Revenge trades
- ML-override van baseline-regels

---

## 9. Waarom dit werkt op XAU/USD

Gold is:

- Manipulatie-gedreven
- Structuur-respecterend
- Liquiditeit-georiënteerd
- Ideaal voor hoge R:R

---

## 10. Architectuur-fit

Dit model hoort in:

- `strategy_modules/ict/`
- `strategies/sqe_xauusd.py`
- Tester → Rapport → Improver loop

**ZONDER** ML-beslissingen.  

**ML mag alleen:**

- configs ranken
- regime labelen
- entries **filteren** (nooit forceren)
