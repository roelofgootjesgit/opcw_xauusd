# Instructie: OpenClaw-bot op de VPS

De **OpenClaw-bot** (oclw_bot) draait op de VPS, voert tests uit en past parameters stapsgewijs aan richting betere KPI’s — vergelijkbaar met een **ML-achtige feedbackloop**: meten → vergelijken → kleine aanpassing → opnieuw meten; alleen verbeteringen accepteren (guardrails).

---

## 1. Doel van de bot

- **Tests uitvoeren** op de VPS (unit, integration, regression, performance).
- **Rapport genereren** (REPORT.md + metrics.json) met KPI’s.
- **Waarden aanpassen** (config/parameters) in kleine stappen, alleen als de KPI’s verbeteren of gelijk blijven (geen verslechtering).
- **Guardrails** handhaven: geen slechtere max drawdown, geen lagere profit factor, geen regressie (winrate, trade count).

---

## 2. Waar draait de bot?

- **Omgeving:** VPS (bijv. systemd-service of cron).
- **Projectroot:** `opclw_xauusd/` (of jouw clone).
- **Relevante mappen:** `configs/`, `scripts/`, `reports/`, `tests/`.

Zorg dat op de VPS o.a. beschikbaar zijn: Python, `pytest`, project-dependencies (`pip install -e .` of `requirements.txt`), en eventueel market data voor de backtest.

---

## 3. Tests uitvoeren op de VPS

### 3.1 Alle tests draaien

```bash
cd /pad/naar/opclw_xauusd
export PYTHONPATH=.
./scripts/run_tests.sh
```

Of direct:

```bash
python -m pytest tests/ -v --tb=short
```

### 3.2 Alleen snelle check (backtest)

```bash
./scripts/run_backtest.sh
# of met specifieke config:
./scripts/run_backtest.sh configs/xauusd.yaml
```

### 3.3 Volledig rapport (tests + backtest + KPI’s)

```bash
python scripts/make_report.py
```

Dit schrijft:

- `reports/latest/REPORT.md` — status (PASS/FAIL), failed tests, KPI-tabel.
- `reports/latest/metrics.json` — run_id, git_commit, tests (passed/failed), kpis (net_pnl, profit_factor, max_drawdown, winrate, expectancy_r, trade_count, avg_holding_hours).

**Eerste keer (golden referentie):**

```bash
python scripts/make_report.py --baseline
```

Dit zet ook `reports/history/baseline.json`. Die baseline gebruik je voor regressie en voor “waarden aanpassen naar succes”: alleen wijzigingen accepteren die niet slechter zijn dan de baseline (binnen de guardrails).

---

## 4. Waarden aanpassen naar succes (ML-achtige loop)

De bot past **geen** willekeurige wijzigingen door. Het idee is: **feedback = KPI’s**; **actie = kleine parameter-/config-wijziging**; **beloning = alleen behouden als beter of gelijk**.

### 4.1 Welke waarden kun je aanpassen?

In **configs/** (bijv. `configs/default.yaml`, `configs/xauusd.yaml`):

| Waarde | Betekenis | Richting “succes” (vaak) |
|--------|-----------|---------------------------|
| `backtest.tp_r` | Take-profit (in R) | Zoeken: niet te laag (weinig winst), niet te hoog (te weinig hits). |
| `backtest.sl_r` | Stop-loss (in R) | Lager = strakker risico; hoger = meer ruimte, meer drawdown. |
| `backtest.default_period_days` | Backtest-periode | Minimaal gelijk aan baseline (geen overfit op korte periode). |
| `risk.max_position_pct` | Max positiegrootte | Lager = minder drawdown, minder rendement. |
| `risk.max_daily_loss_r` | Max dagverlies (R) | Lager = strenger risico. |

Andere strategy-specifieke parameters staan in dezelfde config (bijv. onder `strategy:`).

### 4.2 Stappen: meten → vergelijken → aanpassen → opnieuw meten

1. **Meten**
   - `python scripts/make_report.py`
   - Lees `reports/latest/metrics.json` en eventueel `REPORT.md`.

2. **Vergelijken met baseline**
   - Lees `reports/history/baseline.json`.
   - Vergelijk: net_pnl, profit_factor, max_drawdown, winrate, expectancy_r, trade_count.

3. **Beslissen**
   - **Als alle tests groen zijn en KPI’s ≥ baseline (binnen guardrails):** huidige waarden zijn “succes”; eventueel deze run als nieuwe baseline zetten na bewuste release (`make_report.py --baseline`).
   - **Als KPI’s slechter:** wijziging **niet** accepteren; config/parameters terugzetten (rollback).

4. **Waarden aanpassen (kleine stappen)**
   - Max **1–3** parameters per iteratie aanpassen (bijv. alleen `tp_r` of alleen `sl_r`).
   - Kleine stappen (bijv. tp_r: 2.0 → 2.2 of 1.8), dan opnieuw punt 1–3.

5. **Herhalen**
   - Op de VPS kan dit geautomatiseerd: bijvoorbeeld na elke wijziging `make_report.py` draaien, metrics vergelijken, alleen bij verbetering behouden.

### 4.3 Guardrails (geen change accepteren als)

- **Max drawdown** slechter dan baseline/drempel.
- **Profit factor** onder minimum (bijv. &lt; 1.0 of onder baseline).
- **Regressietests falen:** winrate &gt;2% daling t.o.v. baseline, trade count &gt;20% stijging (overtrading).
- Geen verbetering op een **te korte** backtest-periode (overfit-risico).

Zie ook `oclw_bot/rules.md` voor de volledige regels.

---

## 5. Automatisering op de VPS

### 5.1 Periodiek rapport (bijv. cron)

```bash
# Dagelijks om 06:00
0 6 * * * cd /pad/naar/opclw_xauusd && python scripts/make_report.py >> /var/log/opclaw/report.log 2>&1
```

### 5.2 Na code/config-wijziging

- Na push of na handmatige parameter-aanpassing: `python scripts/make_report.py`.
- Als status PASS en KPI’s binnen guardrails: wijziging behouden.
- Als FAIL of KPI’s slechter: rollback en oorzaak analyseren (zie Improver-Agent in `oclw_bot/prompts/improver.md`).

### 5.3 Eerste keer

1. Data beschikbaar maken (indien van toepassing, bijv. `oclw_bot fetch` of handmatig).
2. `./scripts/run_tests.sh` en `./scripts/run_backtest.sh` controleren.
3. `python scripts/make_report.py --baseline` om de baseline te zetten.

---

## 6. Samenvatting: “Executeert tests en past values aan naar succes als ML”

| Stap | Actie |
|------|--------|
| 1 | Op VPS: `python scripts/make_report.py` (tests + backtest + rapport). |
| 2 | Metrics uitlezen uit `reports/latest/metrics.json` en vergelijken met `reports/history/baseline.json`. |
| 3 | Als FAIL of KPI’s slechter: geen waarden aanpassen behouden; rollback. |
| 4 | Als PASS en KPI’s ok: eventueel 1–3 parameters in `configs/` in kleine stappen aanpassen. |
| 5 | Opnieuw `make_report.py` draaien; alleen bij verbetering (of gelijk) de nieuwe waarden accepteren. |
| 6 | Herhalen tot gewenste KPI’s of tot geen verbetering meer (lokaal optimum). |

De **Tester-Agent** (`oclw_bot/prompts/tester.md`) doet tests en rapporten; de **Improver-Agent** (`oclw_bot/prompts/improver.md`) leest het rapport en doet kleine fixes/parameter-aanpassingen met guardrails. Beide volgen `oclw_bot/rules.md`.

---

## 7. Verwijzingen

- **VPS-loop (overzicht):** `docs/VPS_LOOP.md`
- **Bot-regels:** `oclw_bot/rules.md`
- **Tester-prompt:** `oclw_bot/prompts/tester.md`
- **Improver-prompt:** `oclw_bot/prompts/improver.md`
- **Config-voorbeelden:** `configs/default.yaml`, `configs/xauusd.yaml`
