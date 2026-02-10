#!/usr/bin/env python3
"""
oclw_bot report generator: run tests + backtest, collect KPIs, write REPORT.md and metrics.json.
Usage:
  python scripts/make_report.py                    # write to reports/latest/
  python scripts/make_report.py --baseline        # also save as reports/history/baseline.json
  python scripts/make_report.py --config configs/xauusd.yaml
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )
        return (out.stdout or "").strip()[:12]
    except Exception:
        return "unknown"


def run_pytest() -> tuple[int, int, str]:
    """Run pytest; return (passed, failed, short_output)."""
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=120,
    )
    out = (r.stdout or "") + (r.stderr or "")
    # Count passed/failed from line like "12 passed, 1 skipped" or "10 passed, 2 failed"
    passed = failed = 0
    for line in out.strip().split("\n"):
        if "passed" in line and ("failed" in line or "skipped" in line or "in " in line):
            try:
                parts = line.replace(",", " ").split()
                for i, p in enumerate(parts):
                    if p == "passed" and i > 0:
                        passed = int(parts[i - 1])
                    elif p == "failed" and i > 0:
                        failed = int(parts[i - 1])
            except (ValueError, IndexError):
                pass
            break
    return passed, failed, out[-2000:] if len(out) > 2000 else out


def run_backtest_and_metrics(config_path: str | None, period_days: int | None = None) -> dict:
    """Run backtest, return metrics dict for KPIs."""
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from src.trader.config import load_config
    from src.trader.backtest.engine import run_backtest
    from src.trader.backtest.metrics import compute_metrics
    cfg = load_config(config_path)
    if period_days is not None:
        cfg.setdefault("backtest", {})["default_period_days"] = period_days
    trades = run_backtest(cfg)
    m = compute_metrics(trades)
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description="oclw_bot report generator")
    ap.add_argument("--baseline", action="store_true", help="Save metrics as baseline.json")
    ap.add_argument("--config", "-c", default=None, help="Config YAML path for backtest")
    ap.add_argument("--days", "-d", type=int, default=None, help="Override backtest period (days), e.g. 30 for 1 month")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from src.trader.config import load_config as _load_cfg
    from src.trader.logging_config import setup_logging
    setup_logging(_load_cfg(args.config))
    latest_dir = root / "reports" / "latest"
    history_dir = root / "reports" / "history"
    latest_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_log = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")  # same as oclw_bot_<ts>.log
    git_commit = get_git_commit()
    logs_dir = root / "logs"
    json_dir = root / "logs" / "json"
    logs_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    # 1) Run tests
    passed, failed, test_output = run_pytest()
    tests_ok = failed == 0

    # 2) Run backtest and get KPIs
    try:
        kpis = run_backtest_and_metrics(args.config, period_days=args.days)
    except Exception as e:
        kpis = {
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "winrate": 0.0,
            "expectancy_r": 0.0,
            "trade_count": 0,
            "error": str(e),
        }
    winrate_01 = kpis.get("win_rate_01") or (kpis.get("win_rate", 0) / 100.0)
    metrics_payload = {
        "run_id": run_id,
        "git_commit": git_commit,
        "tests": {"passed": passed, "failed": failed},
        "kpis": {
            "net_pnl": kpis.get("net_pnl", 0),
            "profit_factor": kpis.get("profit_factor", 0),
            "max_drawdown": kpis.get("max_drawdown", 0),
            "winrate": winrate_01,
            "win_rate_pct": kpis.get("win_rate", 0),
            "expectancy_r": kpis.get("expectancy_r", 0),
            "trade_count": kpis.get("trade_count", 0) or kpis.get("total_trades", 0),
            "avg_holding_hours": kpis.get("avg_holding_hours", 0),
        },
    }

    # 3) Write metrics.json (reports/latest) and logs/json/ for data collection
    (latest_dir / "metrics.json").write_text(
        json.dumps(metrics_payload, indent=2, default=str),
        encoding="utf-8",
    )
    json_path = json_dir / f"run_{ts_log}.json"
    json_path.write_text(json.dumps(metrics_payload, indent=2, default=str), encoding="utf-8")
    if args.baseline:
        (history_dir / "baseline.json").write_text(
            json.dumps(metrics_payload, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"[make_report] Baseline saved to reports/history/baseline.json")

    # 4) Write REPORT.md (reports/latest) and report as .log (logs/)
    status = "PASS" if tests_ok and kpis.get("error") is None else "FAIL"
    md_lines = [
        "# oclw_bot Report",
        "",
        f"**Run ID:** {run_id}  \n**Git:** `{git_commit}`  \n**Status:** {status}",
        "",
        "## Summary",
        f"- Tests: {passed} passed, {failed} failed",
        f"- KPIs: net_pnl={kpis.get('net_pnl', 0):.2f}, PF={kpis.get('profit_factor', 0):.2f}, "
        f"winrate={kpis.get('win_rate', 0):.1f}%, max_dd={kpis.get('max_drawdown', 0):.2f}R, "
        f"trades={metrics_payload['kpis']['trade_count']}",
        "",
        "## Failed tests (last run)",
        "```",
        test_output[-1500:] if test_output else "(no output)",
        "```",
        "",
        "## KPIs (this run)",
        "| Metric | Value |",
        "|--------|-------|",
        f"| net_pnl | {metrics_payload['kpis']['net_pnl']} |",
        f"| profit_factor | {metrics_payload['kpis']['profit_factor']:.2f} |",
        f"| max_drawdown | {metrics_payload['kpis']['max_drawdown']:.2f} |",
        f"| winrate | {metrics_payload['kpis']['win_rate_pct']:.1f}% |",
        f"| expectancy_r | {metrics_payload['kpis']['expectancy_r']:.2f} |",
        f"| trade_count | {metrics_payload['kpis']['trade_count']} |",
        f"| avg_holding_hours | {metrics_payload['kpis']['avg_holding_hours']:.2f} |",
        "",
        "## Next actions",
        "- If FAIL: fix failing tests or backtest error before merging.",
        "- If PASS and KPIs improved: accept change. If KPIs worse: reject (guardrails).",
        "",
    ]
    (latest_dir / "REPORT.md").write_text("\n".join(md_lines), encoding="utf-8")
    log_path = logs_dir / f"oclw_bot_{ts_log}.log"
    log_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[make_report] Report: {log_path}")
    print(f"[make_report] Data:   {json_path}")
    print(f"[make_report] Also: reports/latest/REPORT.md and metrics.json")
    if not tests_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
