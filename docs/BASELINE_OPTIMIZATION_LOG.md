# Baseline Optimalisatie Log — XAUUSD SQE Strategie

**Periode:** 2026-02-10 t/m 2026-02-15  
**Doel:** Baseline strategie stabiliseren voordat ML-lagen worden toegevoegd  
**Status:** Lopend — regime_profiles uitgeschakeld als werkwijziging, hervalidatie nodig

---

## Aanleiding

Het oorspronkelijke plan was om vier ML-lagen bovenop de ICT-strategie te bouwen:
regime classifier, trade filter, entry timer, en Optuna config optimizer.

Tijdens review werd vastgesteld dat dit prematuur was. De baseline strategie had
fundamentele problemen:

- **ATR-SL inconsistentie:** SL varieerde factor 7.5x ($7.87 — $59.40), niet
  gekoppeld aan structuur-invalidatiepunten
- **Sessie-classificatiebug:** 07:15 UTC werd als Asia gelabeld terwijl dat London
  open is
- **Lage expectancy:** PF = 0.47, WR = 20%, expectancy negatief
- **Regime profiles:** ongevalideerde TP/SL modulatie per regime (trending/ranging/volatile)

**Besluit:** Eerst baseline canonicaliseren. Geen ML tot baseline stabiel is.

---

## Discipline-kader

Elke wijziging volgt dit protocol:

1. **Eén variabele per iteratie** — nooit twee dingen tegelijk wijzigen
2. **Hypothese vooraf** — strak geformuleerd, met reject-criteria
3. **KPI's die beslissen:** PF, expectancy_r, max_dd, trade_count
4. **Guardrails:** max_dd niet slechter, trade_count ±20% van baseline, PF niet onder baseline
5. **Bij falen: revert** — geen dooroptimaliseren op gefaalde hypothese

---

## Iteratie 1: Sessie-integriteit fix

**Hypothese:** "Als we killzone-uren corrigeren naar juiste UTC (London 07-10, NY 12-15),
verbetert sessie-classificatie en dedup-logica."

**Wijziging:**
- `src/trader/data/sessions.py`: UTC-uren gecorrigeerd (bugfix)
- `configs/xauusd.yaml`: `session_filter: [London, "New York"]` geactiveerd

**Resultaat:**
- Bugfix sessions.py: correcte classificatie — **behouden**
- Session_filter actief: trade_count 14 → 2 (-85.7%) — **gerejected, gerevert**

**Conclusie:** De strategie produceert setups buiten killzones. Killzone-filter is
nu geen filter maar edge-amputatie. Sessions.py bugfix = integriteitsfix (behouden).
Session_filter = pas later, wanneer entry-logica aligned is met killzones.

---

## Iteratie 2: Sweep-anchored SL

**Hypothese:** "Als we SL op het sweep-invalidatiepunt zetten i.p.v. ATR, verbetert
DD-stabiliteit omdat stops op structuur staan."

**Wijziging:**
- `liquidity_sweep.py`: `swept_low`/`swept_high` columns toegevoegd
- `sqe_xauusd.py`: `return_details` parameter, forward-fill van sweep levels
- `engine.py`: SL = sweep level + buffer, "no sweep = no trade"

**Resultaat:** 0 trades. Reden: `min_count=2` laat entries toe zonder sweep
(displacement + FVG volstaat). Sweep-anchored SL vereist sweep-anker dat er
niet altijd is.

**Conclusie:** Contract mismatch tussen entry-logica en risk-model. Sweep-SL is
logisch onmogelijk zolang sweep niet verplicht is voor elke entry. **Gerevert.**

---

## Iteratie 3: Entry-contract canonicaliseren (sweep mandatory)

**Hypothese:** "Als sweep verplicht is voor elke entry, stijgt kwaliteit omdat
we alleen manipulation→reaction trades nemen."

**Wijziging:**
- `sqe_xauusd.py`: sweep als harde AND-conditie voor entry
- `xauusd.yaml`: lookback 5 → 15 bars

**Resultaat:** 0 entries. Sweep + displacement + FVG + structure alignen te
zeldzaam, zelfs met ruimere lookback.

**Conclusie:** De volledige ICT-sequentie is te restrictief voor deze markt/timeframe
combinatie. De strategie werkt al op een subset van de sequentie. **Gerevert.**

---

## Iteratie 4: Filter ablation analyse

**Doel:** Begrijpen welke filterlaag hoeveel signalen blokkeert.

**Methode:** Systematisch filters aan/uit zetten, signaalcount meten.

**Resultaten:**

| Filter | Effect op signalen |
|--------|-------------------|
| H1-gate | -42% (54% LONG, 12% SHORT geblokkeerd) |
| Dedup | -78% (37→9 LONG, 28→5 SHORT) |
| Session filter | 0% (stond uit) |

**Conclusie:** H1-gate blokkeert op "afwezigheid van matching structure"
(H1=neutral/range), niet op "expliciet tegengestelde structure". Dedup clustert
correct. De H1-gate is de grootste bron van signaalverlies.

---

## Iteratie 5: Soft H1-gate

**Hypothese:** "Als H1-gate alleen blokkeert bij expliciet tegengestelde structuur
(niet bij RANGE), stijgt trade_count en PF."

**Wijziging:**
- `engine.py`: `_apply_h1_gate` gewijzigd — LONG alleen geblokkeerd als H1
  = BEARISH, niet als RANGE

**Resultaat:**
- trade_count: 14 → 22 (+57%)
- PF: 0.47 → 0.95
- expectancy_r: -0.424 → -0.03
- max_dd: -3.80R → -5.13R (**slechter**)
- 4x LONG loss cluster in 26-27 jan distributieperiode

**Conclusie:** RANGE op H1 ≠ veilig. Het was een "topping range" met lower highs.
De harde H1-gate beschermde tegen regime-onzekerheid. **Gerevert.**

---

## Iteratie 6: Case study 26-27 januari

**Doel:** Root cause van 4x LONG loss cluster vaststellen.

**Methode:** H1 swing-structuur, pivot highs/lows en M15 entries gevisualiseerd
voor de 26-27 jan periode.

**Bevindingen:**
- H1 structure labels waren technisch correct (RANGE bij stabiele lows + lower highs)
- Maar het label-vocabulaire mist "transitional states" (weakening bullish, topping)
- Het probleem is niet de gate, maar de beperkte informatie in het label

**Conclusie:** H1-gate doet zijn werk correct. Het label-systeem is simplistisch
maar niet fout. Geen wijziging nodig.

---

## Iteratie 7: H1 momentum-veto analyse

**Hypothese (van mentor):** "Als we LONG blokkeren bij H1 consecutive lower highs
+ bearish displacement, verminderen drawdown-clusters."

**Methode:** Data-analyse vooraf — meten hoe vaak het veto-signaal voorkomt en
wat het effect is op M15 entries.

**Resultaten:**
- H1 LH active: 51% van de tijd (te veel voor een veto)
- H1 bearish displacement: 2x in 30 dagen (te zeldzaam)
- LH + displacement combo: 3 bars (0.8%), vangt 0 M15 entries
- **Maar:** LH-only is informatief: CLEAN avg_R=+0.60, LH-only avg_R=+0.22

**Conclusie:** Het voorgestelde momentum-veto is een null-operatie. Te zeldzaam
om iets te vangen. LH-state bevat informatie maar is geen veto-signaal.
**Niet geimplementeerd.**

---

## Iteratie 8: Context-aware sizing

**Hypothese (van mentor):** "Als we LH-only trades op halve positie nemen,
daalt max_dd terwijl edge behouden blijft."

**Methode:** Simulatie met echte engine trades, LH-state mapping per trade.

**Resultaat:** 0 van 17 trades is in LH-state. De harde H1-gate filtert alle
LH-context trades al weg.

**Conclusie:** De sizing-aanpassing is een null-operatie. De H1-gate doet al
wat sizing zou moeten doen. **Niet geimplementeerd.**

---

## Iteratie 9: R:R sweep (doorbraak)

**Aanleiding:** Met 17 trades, WR=35%, PF=1.13, expectancy=+0.083R was de edge
flinterdun. De vraag: zit de hefboom in R:R?

**Ontdekking 1 — Regime profiles zijn actief maar onzichtbaar:**
- Trade.regime veld werd niet gezet, maar regime_profiles overschreven TP/SL
- Winners toonden +3.0R (trending), +1.9R (ranging), +1.3R (volatile)
- Regime-specifieke SL/TP was de onzichtbare variabele

**Ontdekking 2 — Regime profiles zijn schadelijk:**

| Scenario | N | WR | PF | Expect_R | Net_R | Max_DD |
|----------|---|-----|------|----------|-------|--------|
| Regime ON (was actief) | 17 | 35.3% | 1.13 | +0.083 | +1.42 | -7.00R |
| Regime OFF, flat tp=2.5 | 17 | 41.2% | 1.75 | +0.441 | +7.50 | -4.00R |

**Root cause:** Drie mechanismen van schade:
1. **Ranging sl_r=0.8** — te strakke SL stopt trades die met sl_r=1.0 overleven
   (Jan 5 07:00 en Jan 20 17:45: LOSS→WIN door ruimere SL)
2. **Volatile R:R=1.33:1** — tp_r=2.0 met sl_r=1.5 geeft kleine winners
3. **Misclassificatie** — regime detector plaatst bars in verkeerde categorie

**Impact:** De -7R drawdown die we 8 iteraties lang probeerden op te lossen via
H1-gates, momentum-vetos en sizing, werd veroorzaakt door regime-specifieke SL
die WR vernietigde.

---

## Iteratie 10: Multi-window validatie

**Wijziging:** `regime_profiles: null` in configs/xauusd.yaml

**Resultaten:**

| Window | N | WR | PF | Expect_R | Max_DD | Guardrail |
|--------|---|-----|------|----------|--------|-----------|
| 30d | 13 | 30.8% | 1.11 | +0.077R | -3.00R | FAIL (PF<1.4, E<0.2R) |
| 60d | 17 | 41.2% | 1.75 | +0.441R | -4.00R | PASS |
| 90d | 17 | 41.2% | 1.75 | +0.441R | -4.00R | PASS (=60d, zelfde data) |

**Split-half 90d:**
- Eerste helft (Jan 2-20): N=4, 3W/1L — te weinig voor conclusie
- Tweede helft (Jan 21-Feb 6): N=13, 4W/9L, PF=1.11 — = 30d window

**Beperking:** Data gaat maar ~45 dagen terug. 60d en 90d zijn dezelfde sample.
Geen onafhankelijke multi-window validatie mogelijk.

---

## Huidige status

**Config:** `regime_profiles: null` — staat als werkwijziging, niet als baseline.

**Wat bewezen is:**
- Regime profiles zijn aantoonbaar schadelijk (ranging SL, volatile R:R)
- Flat tp_r=2.5 sl_r=1.0 is beter op de beschikbare sample
- DD verbetert van -7R naar -4R

**Wat NIET bewezen is:**
- Dat de verbetering robuust is over meerdere onafhankelijke periodes
- Dat PF=1.75 niet periode-specifiek is (3 early-Jan wins drijven het resultaat)
- Dat de strategie fundamenteel winstgevend is (N=17 is onvoldoende)

**Rollback-instructie:** In `configs/xauusd.yaml` staan de originele regime_profiles
als comment. Uncomment om terug te draaien.

---

## Hervalidatie-criteria

Wanneer 60+ dagen forward data beschikbaar is:

1. Draai `scripts/multi_window_validation.py`
2. **Alle** windows moeten passen:
   - PF >= 1.4
   - Expectancy >= 0.2R
   - Max DD >= -5R
3. Split-half moet beide helften positieve expectancy tonen
4. Bij falen: rollback naar regime_profiles

---

## Lessen geleerd

1. **Onzichtbare variabelen zijn de gevaarlijkste.** Regime profiles overschreven
   TP/SL zonder dat dit in trade output zichtbaar was. 8 iteraties lang zochten
   we het probleem in de verkeerde laag.

2. **Diagnose-bias is reëel.** We onderzochten H1-gates, momentum-vetos, sizing,
   entry-sequencing — allemaal logisch, allemaal verkeerd. De data liet pas zien
   wat het probleem was toen we R:R isoleerden.

3. **N=17 is geen bewijs.** Het is een aanwijzing. Elke conclusie op deze sample
   is voorlopig. Discipline betekent: resultaat niet vieren tot het robuust is.

4. **Complexiteit toevoegen is makkelijk. Complexiteit verwijderen levert meer op.**
   De grootste verbetering kwam van iets uitzetten (regime_profiles), niet van
   iets toevoegen.

5. **Het protocol werkt.** Elke iteratie had een hypothese, reject-criteria, en
   een revert-plan. Zonder dat protocol hadden we 8 lagen complexiteit toegevoegd
   in plaats van 1 laag verwijderd.

---

## Iteratie 11: MAE/MFE analyse (edge-anatomie)

**Doel:** Begrijpen of TP en SL structureel aligned zijn met prijsgedrag.

**Bevindingen:**

| Groep | MAE gemiddeld | MAE max | MFE gemiddeld | MFE max | Duur |
|-------|---------------|---------|---------------|---------|------|
| Winners (7) | 0.77R | 0.97R | 3.12R | 4.75R | 18 bars (4.4h) |
| Losers (10) | 1.75R | 2.71R | 0.65R | 1.43R | 4 bars (1.0h) |

- **tp=2.5 zit op de MFE-klif:** 7 trades bereiken 2.5R, slechts 3 bereiken 3.0R
- **sl=1.0 is minimaal levensvatbaar:** 4/7 winners hebben MAE > 0.8R
- **Verliezers zijn echt fout:** 0/10 losers bereikt MFE >= 1.5R
- **Winners zijn langzaam, losers zijn snel:** structureel "dip-then-grind" profiel

**Conclusie:** TP en SL zijn niet willekeurig gekozen maar aligned met
structurele grenzen van de prijsactie. Dit verklaart mechanisch waarom
regime ranging sl_r=0.8 de edge vernietigde.

---

## Iteratie 12: Tijd-gebaseerde exit falsificatie

**Drie hypotheses getest op bestaande 17 trades (puur simulatie):**

### A) Time-stop (exit als na X bars MFE < threshold)
- Elke MFE<0.5R variant kost 2.5-2.9R door het doden van langzame winners
- De Jan 2 trade (+2.5R) heeft MFE < 0.5R bij bar 6-10, pas TP bij bar 25
- **Gefalsificeerd:** time-stop grijpt in waar winners nog opbouwen

### B) Break-even stop (SL naar entry bij MFE >= threshold)
- Alle varianten (1.0R, 1.5R, 2.0R) kosten exact 2.5R
- De Feb 3 trade (+2.5R) bereikt >2R, trekt terug naar entry, gaat alsnog naar TP
- **Gefalsificeerd:** retrace naar entry is normaal gedrag, geen failure

### C) Combinatie time-stop + BE
- Kost 5.19R, PF daalt van 1.75 naar 1.23
- **Gefalsificeerd:** worst of both worlds

**Conclusie:** Het huidige exit-model (pure TP/SL) is al optimaal voor dit
"dip-then-grind" profiel. Binaire profielen houden niet van management.

---

## Afsluitende status (2026-02-15)

Het systeem is nu in een zeldzame toestand:

- **Simpel:** geen verborgen variabelen, geen regime-modulatie
- **Intern consistent:** entry, TP, SL en exit zijn aligned met prijsgedrag
- **Mechanisch onderbouwd:** elke parameter heeft data-evidence
- **Volledig geanalyseerd:** 12 iteraties, 3 gefalsificeerde hypotheses

**Er is niets meer om aan te sleutelen zonder nieuwe data.**

De volgende stap is forward-validatie: 40-60 trades verzamelen zonder
wijzigingen, en statistisch meten of de edge reëel is.

---

## Forward-validatie protocol

### Geen wijzigingen aan config of code tot validatie compleet is.

### Wat te meten (elke 2 weken):
1. Rolling PF (20-trade window)
2. Rolling expectancy (20-trade window)
3. Max consecutive losses
4. WR stabiliteit (moet rond 40% blijven)
5. Max DD progressie

### Acceptatiecriteria (na 40+ trades):
- PF >= 1.3 (iets soepeler dan 1.4 gezien grotere sample)
- Expectancy >= 0.15R
- Max DD <= -6R
- WR >= 35%
- Geen window van 20 trades met PF < 1.0

### Bij falen:
- Als PF < 1.0 na 40 trades: edge is niet reëel. Stop.
- Als DD > -8R: risico te hoog. Halveer positiegrootte.
- Als WR < 25%: entry-logica fundamenteel herzien.

### Wanneer klaar:
- Na 60 trades met stabiele metrics: baseline officieel bevestigd
- Pas dan ML-lagen overwegen (regime als filter, niet als TP/SL modulator)

---

## Bestanden gewijzigd (permanent)

| Bestand | Wijziging | Status |
|---------|-----------|--------|
| `src/trader/data/sessions.py` | UTC killzone-uren gecorrigeerd | Behouden (bugfix) |
| `configs/xauusd.yaml` | `regime_profiles: null` | Werkwijziging (hervalidatie nodig) |
| `src/trader/strategy_modules/ict/liquidity_sweep.py` | `swept_low`/`swept_high` exports | Behouden (infrastructuur) |
| `src/trader/strategies/sqe_xauusd.py` | `return_details` parameter | Behouden (infrastructuur) |

## Bestanden aangemaakt (analyse-scripts)

| Script | Doel |
|--------|------|
| `scripts/h1_momentum_analysis.py` | H1 LH/HL + displacement frequentie-analyse |
| `scripts/sizing_simulation.py` | Context-aware sizing simulatie |
| `scripts/rr_sweep.py` | R:R sweep met/zonder regime profiles |
| `scripts/multi_window_validation.py` | Multi-window validatie (30/60/90d) |
| `scripts/mae_mfe_analysis.py` | MAE/MFE distributie-analyse per trade |
| `scripts/time_exit_analysis.py` | Tijd-gebaseerde exit falsificatie |
