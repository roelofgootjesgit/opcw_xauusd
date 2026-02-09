# oclw_bot Report

**Run ID:** 2026-02-09T16:03:04Z  
**Git:** `34046113a778`  
**Status:** PASS

## Summary
- Tests: 12 passed, 0 failed
- KPIs: net_pnl=0.00, PF=0.00, winrate=0.0%, max_dd=0.00R, trades=0

## Failed tests (last run)
```
============================= test session starts =============================
platform win32 -- Python 3.11.0, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\Gebruiker\opclw_xauusd
configfile: pyproject.toml
plugins: anyio-4.9.0
collected 13 items

tests\integration\test_pipeline.py ..                                    [ 15%]
tests\performance\test_runtime_limits.py .                               [ 23%]
tests\regression\test_baseline_guardrails.py .s                          [ 38%]
tests\test_sqe_smoke.py ...                                              [ 61%]
tests\unit\test_indicators.py .....                                      [100%]

======================== 12 passed, 1 skipped in 8.14s ========================

```

## KPIs (this run)
| Metric | Value |
|--------|-------|
| net_pnl | 0.0 |
| profit_factor | 0.00 |
| max_drawdown | 0.00 |
| winrate | 0.0% |
| expectancy_r | 0.00 |
| trade_count | 0 |
| avg_holding_hours | 0.00 |

## Next actions
- If FAIL: fix failing tests or backtest error before merging.
- If PASS and KPIs improved: accept change. If KPIs worse: reject (guardrails).
