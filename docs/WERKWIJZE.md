# Werkwijze: test draaien, en dan?

**Feb 2026.** Voor volledig overzicht → **docs/PROJECT_STATUS_GPT.md**.

Vaste volgorde: **test draaien → rapport bekijken → vergelijken met baseline → beslissen → eventueel pushen naar VPS.**

---

## 1. Test draaien (lokaal)

```powershell
# Venv actief (eenmalig: python scripts/setup_venv.py)
python scripts/run_full_test.py --report
```

Dit doet: fetch (Yahoo) → backtest → pytest → schrijft **reports/latest/REPORT.md** en **reports/latest/metrics.json**.  
Log staat in **logs/oclw_bot_<datum>_<tijd>.log**.

---

## 2. Rapport bekijken

- **reports/latest/REPORT.md** — status (PASS/FAIL), KPI’s (net_pnl, PF, winrate, max_dd, trade_count).
- **reports/latest/metrics.json** — zelfde cijfers in JSON.

Vragen:
- Zijn de **tests groen** (PASS)?
- Zijn de **KPI’s acceptabel** (geen rare uitschieters)?

---

## 3. Vergelijken met baseline

- **reports/history/baseline.json** — de “gouden” referentie (eerste goede run of laatste geaccepteerde).
- Vergelijk: winrate, trade_count, max_drawdown, profit_factor met de **laatste run** (metrics.json).

**Guardrails (oclw_bot/rules.md):**  
Geen wijziging accepteren als: max DD slechter, PF onder minimum, regressietests rood, trade count >20% stijging (overtrading).

---

## 4. Beslissen: wat nu?

| Situatie | Actie |
|----------|--------|
| **Alles groen, KPI’s ok, geen wijziging nodig** | Klaar. Optioneel: commit + push als je wilt dat VPS dezelfde stand heeft. |
| **Alles groen, KPI’s beter dan baseline** | Nieuwe run als referentie nemen: `python scripts/make_report.py --baseline` → daarna commit + push. |
| **Alles groen, KPI’s slechter** | Wijziging **niet** overnemen. Config/code terugdraaien of verbeteren, opnieuw testen. |
| **Tests rood (FAIL)** | Bug fixen of test aanpassen (met reden), opnieuw `run_full_test.py --report` tot groen. |
| **Wil je parameters/strategie aanpassen** | Config/code wijzigen → opnieuw `run_full_test.py --report` → terug naar stap 2 en 3. |

**Kort:** groen + KPI’s binnen guardrails → mag naar VPS (en eventueel nieuwe baseline). Rood of KPI’s buiten de band → niet pushen, eerst fixen.

---

## 5. Naar VPS (als alles ok is)

1. **Commit + push** (alleen als lokaal groen en KPI’s ok).
2. **Op VPS:** `git pull` → (eerste keer: `python3 scripts/setup_venv.py`, `source .venv/bin/activate`) → `python scripts/make_report.py`.
3. Rapport op VPS staat weer in **reports/latest/**; agents (Tester/Improver) gebruiken dat volgens **oclw_bot/rules.md**.

---

## 6. Eerste keer: baseline zetten

Als je nog **geen** baseline hebt (nieuw project of grote reset):

1. Run: `python scripts/run_full_test.py --report`.
2. Als de run “goed genoeg” is om als referentie te dienen:  
   `python scripts/make_report.py --baseline`  
   → slaat **reports/latest/metrics.json** op als **reports/history/baseline.json**.
3. Daarna: alle volgende runs vergelijken met die baseline (zie stap 3).

---

## Snel-schema

```
run_full_test.py --report
    ↓
REPORT.md + metrics.json bekijken
    ↓
Vergelijk met baseline.json (guardrails)
    ↓
Groen + OK?  → (optioneel) make_report.py --baseline  →  commit + push  →  VPS: pull + make_report
Niet OK?     → fix (config/code)  →  opnieuw run_full_test.py --report
```

Dit is de werkwijze: **test draaien → rapport → vergelijken → beslissen → eventueel baseline + push.**
