"""
Regression tests: strategy output must stay within guardrails vs baseline.
Run with fixed dataset/config; compare KPIs to baseline.json.
"""
import json
import pytest
from pathlib import Path


def test_regression_winrate_not_below_threshold():
    """Win rate may not drop more than 2% vs baseline (if baseline exists)."""
    baseline_path = Path(__file__).resolve().parents[2] / "reports" / "history" / "baseline.json"
    if not baseline_path.exists():
        pytest.skip("No baseline.json yet; create one with make_report.py --baseline")
    from src.trader.config import load_config
    from src.trader.backtest.engine import run_backtest
    from src.trader.backtest.metrics import compute_metrics
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    kpis_b = baseline.get("kpis", {})
    baseline_winrate = kpis_b.get("winrate") or (kpis_b.get("win_rate_pct", 0) or kpis_b.get("win_rate", 0)) / 100.0
    cfg = load_config()
    trades = run_backtest(cfg)
    metrics = compute_metrics(trades)
    current_winrate = metrics.get("win_rate", 0) / 100.0
    assert current_winrate >= baseline_winrate - 0.02, "Win rate dropped >2% vs baseline"


def test_regression_trade_count_not_exploded():
    """Trade count may not exceed baseline by >20% (overtrading guard)."""
    baseline_path = Path(__file__).resolve().parents[2] / "reports" / "history" / "baseline.json"
    if not baseline_path.exists():
        pytest.skip("No baseline.json yet")
    from src.trader.config import load_config
    from src.trader.backtest.engine import run_backtest
    from src.trader.backtest.metrics import compute_metrics
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    cfg = load_config()
    trades = run_backtest(cfg)
    metrics = compute_metrics(trades)
    kpis_b = baseline.get("kpis", {})
    baseline_count = kpis_b.get("trade_count", 0) or kpis_b.get("total_trades", 0)
    if baseline_count == 0:
        pytest.skip("Baseline has no trades")
    current_count = metrics.get("trade_count", 0) or metrics.get("total_trades", 0)
    assert current_count <= baseline_count * 1.20, "Trade count >20% above baseline (overtrading)"
