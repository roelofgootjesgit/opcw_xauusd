# OpenClaw Agent Instructie (ENIGE instructie — lees NIETS anders)

## STOP. Lees alleen dit bestand en volg de stappen hieronder. Lees GEEN andere docs, code, of bestanden.

---

## Jouw taak

Je bent een ML-achtige optimalisatie-agent. Je doet 3 dingen:

1. **Run** het test-script
2. **Lees** het compacte rapport (llm_input.json)
3. **Besluit** (JSON): accepteer, verwerp, of stel 1-3 parameter-wijzigingen voor

Dat is alles. Geen uitleg. Geen verkenning. Geen andere bestanden lezen.

---

## Stap 1: Test draaien

```bash
cd /pad/naar/opclw_xauusd
source .venv/bin/activate
python scripts/run_full_test.py --days 30 --config configs/xauusd.yaml --report
python scripts/make_llm_input.py --config configs/xauusd.yaml
```

## Stap 2: Rapport lezen

Lees **ALLEEN** dit bestand:

```
reports/latest/llm_input.json
```

Dit bevat alles wat je nodig hebt:
- Status (PASS/FAIL)
- KPI's (net_pnl, profit_factor, max_drawdown, winrate, trade_count)
- Delta vs baseline
- Guardrail flags (DD_WORSE, PF_BELOW_1, OVERTRADING, NO_TRADES, etc.)
- Allowed knobs (welke parameters je mag aanpassen, met min/max)
- Cooldown status

**LEES GEEN andere bestanden.** Geen logs, geen code, geen configs, geen docs.

## Stap 3: Beslissen (strict JSON)

Antwoord ALLEEN met dit JSON-formaat:

### Bij PASS + geen guardrail flags:
```json
{
  "decision": "ACCEPT",
  "reason_codes": ["ALL_GREEN"],
  "changes": [],
  "notes": ""
}
```

### Bij guardrail flags of gewenste verbetering:
```json
{
  "decision": "PROPOSE_CHANGE",
  "reason_codes": ["NO_TRADES"],
  "changes": [
    {"path": "strategy.liquidity_sweep.sweep_threshold_pct", "from": 0.15, "to": 0.12}
  ],
  "notes": "sweep drempel verlaagd voor meer trades"
}
```

### Bij cooldown = true:
```json
{
  "decision": "STOP",
  "reason_codes": ["COOLDOWN"],
  "changes": [],
  "notes": "3x 0 trades, handmatige analyse nodig"
}
```

## Stap 4: Wijziging toepassen

Sla je JSON-beslissing op als `decision.json` en run:

```bash
python scripts/apply_changes.py decision.json --config configs/xauusd.yaml --re-run
```

Dit script:
- Valideert dat je changes binnen allowed_knobs vallen
- Past de YAML-config aan
- Draait automatisch make_report.py opnieuw
- Logt de beslissing in logs/json/

## Stap 5: Herhaal vanaf Stap 1

---

## Regels (NIET ONDERHANDELBAAR)

1. **Max 1-3 parameter-wijzigingen per iteratie**
2. **Alleen parameters uit `allowed_knobs`** — alles daarbuiten wordt geweigerd
3. **Bij cooldown: STOP** — geen verdere wijzigingen
4. **Max 10 runs per dag** — check `runs_today` in llm_input.json
5. **Antwoord ALLEEN in JSON** — geen uitleg, geen reflectie, geen essays
6. **Lees GEEN andere bestanden** — llm_input.json is je enige input
7. **Geen strategy rewrites** — alleen config parameter tweaks
8. **Geen code wijzigingen** — alleen configs/xauusd.yaml via apply_changes.py

---

## Guardrail flags en wat te doen

| Flag | Betekenis | Actie |
|------|-----------|-------|
| `NO_TRADES` | 0 trades in backtest | Versoepel filters: sweep_threshold_pct omlaag, min_move_pct omlaag, of entry_sweep_disp_fvg_min_count: 3→2 |
| `DD_WORSE` | Max drawdown slechter dan baseline | Versterk filters: require_structure=true, H1 gate aan, of strengere entry |
| `PF_BELOW_1` | Profit factor onder 1.0 | Verbeter TP/SL ratio: tp_r omhoog, of strengere entries |
| `PF_REGRESSION` | PF >10% slechter dan baseline | Laatste wijziging terugdraaien |
| `WINRATE_DROP` | Winrate >2% gedaald | Laatste wijziging terugdraaien of entry soepeler |
| `OVERTRADING` | >20% meer trades dan baseline | Versterk filters |
| Geen flags + PASS | Alles ok | ACCEPT |
