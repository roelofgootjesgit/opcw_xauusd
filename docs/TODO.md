# TODO

**Status:** Feb 2026. Zie **docs/PROJECT_STATUS_GPT.md** voor huidige fase.

- [ ] Add MT5/Oanda connector behind `broker_stub`
- [ ] Optional registry for ICT modules (discover and run by name)
- [ ] Session filter (Tokyo/London/NY) in backtest (config: `session_filter` nu `null`)
- [ ] Short-side SQE in engine (currently LONG only)
- [ ] HTML/PDF report output
- [ ] More unit tests for each ICT module and metrics
- [ ] Integrate ML optimize loop into VPS/Improver flow (best_ml_config als voorstel)
- [ ] Telegram: SHOW_REPORT, RUN_SWEEP, APPLY_TWEAK/ROLLBACK (zie TELEGRAM_COMMANDS.md)