# oclw_bot Rules (must-follow)

Deze regels gelden voor de Tester-Agent en Improver-Agent in de VPS Test → Rapport → Verbeter loop.

---

## 0. Canonieke principes (onwijzigbaar)

**Bron:** `docs/OCLW_PRINCIPLES.md`

- **Principe:** Meten → Wachten → Reageren. Geen voorspellen, gokken, compenseren.
- **Kern:** Alleen marktstructuur classificeren, liquiditeit lokaliseren, reactie op manipulatie traden. Alles daarbuiten = **NO TRADE**.
- **Structuur:** RANGE = NO TRADE. Alleen LONGS bij BULLISH_STRUCTURE, alleen SHORTS bij BEARISH_STRUCTURE. Nooit tegen H1-structuur in.
- **Sweep verplicht:** Geen entry zonder liquidity sweep + structure break. Geen sweep = NO TRADE.
- **Risk:** SL boven/onder sweep; TP1 1R, TP2 2R, TP3 tegenoverliggende liquiditeit. Max 1–2 trades per sessie; geen stacking; geen re-entry zonder nieuwe sweep.
- **Sessies:** Alleen London + NY voor entries. Geen Azië-entries; geen CPI/FOMC/high-impact.
- **ML:** Mag alleen configs ranken, regime labelen, entries filteren — **nooit** entries forceren of baseline-regels overriden.

Elke strategie- of execution-wijziging moet binnen deze principes blijven.

---

## 1. Geen strategy rewrite zonder regressietest

- Geen grote refactor van strategie-logica zonder dat er een regressietest bij komt die de oude output vastlegt (baseline) of guardrails (winrate, trade count, max DD) checkt.
- Wijzigingen in `src/trader/strategies/` of `src/trader/strategy_modules/` moeten getest worden via `tests/regression/` en/of uitbreiding van unit/integration tests.

## 2. Geen parameter drift zonder duidelijke KPI-winst

- Config- of parameterwijzigingen (TP/SL, lookback, drempels) alleen doorvoeren als:
  - er een meetbare verbetering is (bijv. PF omhoog, max DD minder slecht, expectancy omhoog), én
  - regressietests groen blijven (geen >2% winrate-daling, geen >20% trade-count explosie).

## 3. Elke wijziging moet een doel hebben

- Elke code- of config-change moet:
  - een test toevoegen of verbeteren, of
  - een concrete bug fixen, of
  - een KPI verbeteren (met rapport/baseline als bewijs).
- Geen "cosmetische" of willekeurige wijzigingen.

## 4. Max 1–3 changes per iteratie

- Per verbeter-cyclus maximaal 1–3 kleine, gerichte wijzigingen.
- Geen "mega refactor" in één stap. Grote wijzigingen opsplitsen in stappen, elk met tests + rapport.

## 5. Geen improvement bij te kleine data-periode (overfit-risico)

- Geen verbetering accepteren die alleen op een heel korte of te kleine marktperiode is gevalideerd.
- Minimaal dezelfde periode als de baseline gebruiken; bij twijfel geen parameter-change mergen.

## 6. Guardrails: wanneer geen change accepteren

- **REJECT** (geen merge / rollback) als:
  - Max drawdown slechter wordt dan de ingestelde drempel (bijv. slechter dan baseline + marge).
  - Profit factor daalt onder het minimum (bijv. < 1.0 of onder baseline).
  - Regressietests falen (winrate >2% daling, trade count >20% stijging, etc.).
  - Overtrading: trade count explodeert zonder duidelijke verbetering van expectancy/PF.

## 7. Rapport en baseline

- Rapport: `reports/latest/REPORT.md` en `reports/latest/metrics.json`.
- Baseline: `reports/history/baseline.json` — golden referentie; alleen updaten na bewuste, gevalideerde release.
- Verbeteringen altijd vergelijken met baseline (of vorige run) voordat je accepteert.

## 8. Rollen

- **Tester-Agent:** tests uitbreiden, runnen, rapport genereren. Geen strategie- of parameterwijzigingen.
- **Improver-Agent:** rapport lezen, root-cause analyse, kleine fixes voorstellen en doorvoeren, tests opnieuw runnen. Alleen mergen als alles groen is en KPI's binnen guardrails vallen.
