# Telegram command set (OpenClaw gateway)

**Feb 2026.** Overzicht project en scripts: **docs/PROJECT_STATUS_GPT.md**.

Eerste module: **RUN_BACKTEST → report terug**. Geen Improver, geen ML.

---

## Commando’s

| Commando | Beschrijving | Expected output |
|----------|--------------|------------------|
| `/run_backtest` | Backtest met default config (`configs/xauusd.yaml`), stuur report terug | "Backtest started…" → daarna report (MD) of kern-metrics |
| `/run_backtest configs/other.yaml` | Backtest met opgegeven config | Idem |
| `RUN_BACKTEST` | Zelfde als `/run_backtest` (zonder slash) | Idem |
| `/help` | Toon beschikbare commando’s | Korte lijst met run_backtest en help |

---

## Expected output (normale flow)

1. **Direct na commando (< 5s):**  
   `Backtest started (run_<ts>). Wait…`

2. **Na afloop:**  
   - **Succes:** Report in Markdown (run_id, git, config, KPIs-tabel). Bij te lange tekst: truncate + "(truncated)".
   - **Fout:** `Backtest failed.` + eventueel error uit `metrics.json`.
   - **Timeout:** `Backtest timed out after 300s.`
   - **Lock:** `Backtest already running. Try again later.`

---

## Failure modes

| Situatie | Gedrag |
|----------|--------|
| Dubbele runs tegelijk | Lock: tweede run krijgt "Backtest already running". |
| Runaway runtime | Subprocess timeout 300s → kill → "Backtest timed out". |
| Report ontbreekt | Pipeline breekt niet: fallback naar metrics-only summary in chat. |
| Geen token | Script exit met "Set TELEGRAM_BOT_TOKEN". |

---

## Setup (VPS)

```bash
# Optional dependency
pip install ".[telegram]"

# .env of export
TELEGRAM_BOT_TOKEN=123:ABC...

# Run (foreground)
python scripts/telegram_listener.py
```

Voor productie: systemd of supervisor zodat de listener herstart bij crash.

---

## Volgende stappen (niet in deze module)

- SHOW_REPORT — laatste report tonen zonder nieuwe run
- RUN_SWEEP — parameter sweep
- APPLY_TWEAK / ROLLBACK — Improver-koppeling
