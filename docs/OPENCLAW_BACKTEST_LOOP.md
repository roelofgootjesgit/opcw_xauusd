# OpenClaw: Backtest runnen en aanpassen voor betere uitkomst

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

## 4. Korte loop voor de bot

1. **Run:** `python scripts/run_full_test.py --days 30 --config configs/xauusd.yaml`
2. **Lees** nieuwste `logs/oclw_bot_*.log` → regel met `Backtest result:` en eventueel trade-regels.
3. **Vergelijk** met vorige run: net_pnl, profit_factor, winrate, max_dd, trade_count.
4. **Besluit:**  
   - 0 trades → filters soepeler in `configs/xauusd.yaml`.  
   - Slechtere KPIs → wijziging terugdraaien of andere kleine aanpassing (strenger/selectiever).  
   - Betere of gelijke KPIs (binnen guardrails) → wijziging behouden, eventueel volgende iteratie.
5. **Herhaal** vanaf stap 1.

Voor volledige instructie en VPS: zie `docs/INSTRUCTIE_OPENCLAW_BOT.md`.
