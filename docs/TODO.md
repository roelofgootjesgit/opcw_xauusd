# TODO

**Status:** Feb 2026. Zie **docs/PROJECT_STATUS_GPT.md** voor huidige fase.
Zie **docs/BASELINE_OPTIMIZATION_LOG.md** voor het optimalisatie-traject.

---

## Huidige prioriteit: Forward-validatie

- [ ] 40-60 trades verzamelen zonder wijzigingen aan config of code
- [ ] Elke 2 weken: rolling PF, rolling expectancy, max consecutive losses meten
- [ ] Na 40+ trades: `scripts/multi_window_validation.py` opnieuw draaien
- [ ] Acceptatiecriteria: PF>=1.3, E>=0.15R, DD<=-6R, WR>=35%
- [ ] Bij falen: rollback regime_profiles (instructies in xauusd.yaml)

## Afgerond (feb 2026)

- [x] Sessions.py bugfix (UTC killzone-uren gecorrigeerd)
- [x] Regime_profiles uitgeschakeld (was schadelijke TP/SL modulatie)
- [x] MAE/MFE analyse (tp=2.5 en sl=1.0 mechanisch onderbouwd)
- [x] Exit-management gefalsificeerd (time-stop, BE, combo — allemaal schadelijk)
- [x] Short-side SQE in engine (werkt, niet meer LONG-only)
- [x] H1-gate gevalideerd (harde gate is correct, soft gate gefalsificeerd)
- [x] BASELINE_OPTIMIZATION_LOG.md geschreven (12 iteraties gedocumenteerd)

## Na forward-validatie

- [ ] Baseline officieel bevestigen (als metrics stabiel)
- [ ] Regime-detectie v2 overwegen: alleen als sizing-modulator, nooit SL/TP override
- [ ] ML-cycle integreren in VPS/Improver flow (best_ml_config als voorstel)

## Infrastructuur (geen prioriteit nu)

- [ ] Add MT5/Oanda connector behind `broker_stub`
- [ ] HTML/PDF report output
- [ ] More unit tests for each ICT module and metrics
- [ ] Telegram: SHOW_REPORT, RUN_SWEEP, APPLY_TWEAK/ROLLBACK
- [ ] Optional registry for ICT modules (discover and run by name)
