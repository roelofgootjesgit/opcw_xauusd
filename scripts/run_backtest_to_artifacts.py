#!/usr/bin/env python3
"""
Run backtest and write report to logs/ (.log) and data to logs/json/ (.json).
Optionally also write to --out for Telegram/OpenClaw.
Usage:
  python scripts/run_backtest_to_artifacts.py --config configs/xauusd.yaml
  python scripts/run_backtest_to_artifacts.py --config configs/xauusd.yaml --out artifacts/run_<ts>
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_timestamp() -> str:
    """Same format as logs: oclw_bot_2026-02-10_20-40-12.log"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")


def run_backtest_and_write_artifacts(
    config_path: str,
    out_dir: Path | None,
    timeout_seconds: int | None = None,
) -> dict:
    """Run backtest; write report to logs/oclw_bot_<ts>.log, JSON to logs/json/run_<ts>.json; optional --out dir."""
    root = _project_root()
    sys.path.insert(0, str(root))

    from src.trader.config import load_config
    from src.trader.backtest.engine import run_backtest
    from src.trader.backtest.metrics import compute_metrics

    ts = _run_timestamp()
    logs_dir = root / "logs"
    json_dir = root / "logs" / "json"
    logs_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_config(config_path)
    if timeout_seconds:
        start = time.monotonic()
        def check_timeout():
            if time.monotonic() - start > timeout_seconds:
                raise TimeoutError(f"Backtest exceeded {timeout_seconds}s")
        trades = run_backtest(cfg)
        check_timeout()
    else:
        trades = run_backtest(cfg)

    metrics = compute_metrics(trades)

    equity_rows = []
    cum_r = 0.0
    for t in trades:
        cum_r += t.profit_r
        equity_rows.append({"timestamp": str(t.timestamp_close), "cumulative_r": round(cum_r, 4)})

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    git_commit = _git_commit(root)

    payload = {
        "run_id": run_id,
        "git_commit": git_commit,
        "config": config_path,
        "kpis": {
            "net_pnl": metrics.get("net_pnl", 0),
            "profit_factor": metrics.get("profit_factor", 0),
            "max_drawdown": metrics.get("max_drawdown", 0),
            "winrate": metrics.get("win_rate", 0) / 100.0,
            "win_rate_pct": metrics.get("win_rate", 0),
            "expectancy_r": metrics.get("expectancy_r", 0),
            "trade_count": metrics.get("trade_count", 0),
            "avg_holding_hours": metrics.get("avg_holding_hours", 0),
        },
    }

    # Report (mens): logs/oclw_bot_YYYY-MM-DD_HH-MM-SS.log
    report_lines = [
        f"{run_id} - backtest - Run ID: {run_id}  Git: {git_commit}  Config: {config_path}",
        f"{run_id} - backtest - KPIs: net_pnl={payload['kpis']['net_pnl']:.2f} PF={payload['kpis']['profit_factor']:.2f} "
        f"winrate={payload['kpis']['win_rate_pct']:.1f}% max_dd={payload['kpis']['max_drawdown']:.2f}R "
        f"trades={payload['kpis']['trade_count']} expectancy_r={payload['kpis']['expectancy_r']:.2f}",
        "## KPIs",
        "| Metric | Value |",
        "|--------|-------|",
        f"| net_pnl | {payload['kpis']['net_pnl']} |",
        f"| profit_factor | {payload['kpis']['profit_factor']:.2f} |",
        f"| max_drawdown | {payload['kpis']['max_drawdown']:.2f} |",
        f"| winrate | {payload['kpis']['win_rate_pct']:.1f}% |",
        f"| expectancy_r | {payload['kpis']['expectancy_r']:.2f} |",
        f"| trade_count | {payload['kpis']['trade_count']} |",
        f"| avg_holding_hours | {payload['kpis']['avg_holding_hours']:.2f} |",
    ]
    log_path = logs_dir / f"oclw_bot_{ts}.log"
    log_path.write_text("\n".join(report_lines), encoding="utf-8")

    # Data (ML): logs/json/run_YYYY-MM-DD_HH-MM-SS.json
    json_path = json_dir / f"run_{ts}.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "metrics.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        (out_dir / "report.md").write_text("\n".join(report_lines), encoding="utf-8")
        with open(out_dir / "equity.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp", "cumulative_r"])
            w.writeheader()
            w.writerows(equity_rows)

    payload["_log_path"] = str(log_path)
    payload["_json_path"] = str(json_path)
    return payload


def _git_commit(root: Path) -> str:
    try:
        import subprocess
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=root,
            timeout=5,
        )
        return (r.stdout or "").strip()[:12]
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run backtest; write report to logs/*.log and data to logs/json/*.json")
    ap.add_argument("--config", "-c", default="configs/xauusd.yaml", help="Config YAML path")
    ap.add_argument("--out", "-o", default=None, help="Also write metrics/report/equity to this dir (e.g. for Telegram)")
    ap.add_argument("--timeout", "-t", type=int, default=None, help="Max runtime in seconds (run in same process)")
    args = ap.parse_args()

    root = _project_root()
    out_dir = None
    if args.out:
        out_dir = Path(args.out)
        if not out_dir.is_absolute():
            out_dir = root / out_dir

    try:
        payload = run_backtest_and_write_artifacts(
            args.config,
            out_dir,
            timeout_seconds=args.timeout,
        )
        print(f"[run_backtest_to_artifacts] Report: {payload.get('_log_path', '')}")
        print(f"[run_backtest_to_artifacts] Data:   {payload.get('_json_path', '')}")
        if out_dir:
            print(f"[run_backtest_to_artifacts] Out:   {out_dir}")
        return 0
    except TimeoutError as e:
        print(f"[run_backtest_to_artifacts] {e}", file=sys.stderr)
        return 124
    except Exception as e:
        print(f"[run_backtest_to_artifacts] Error: {e}", file=sys.stderr)
        ts = _run_timestamp()
        (root / "logs").mkdir(parents=True, exist_ok=True)
        (root / "logs" / "json").mkdir(parents=True, exist_ok=True)
        err_payload = {"error": str(e), "run_id": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        (root / "logs" / "json" / f"run_{ts}.json").write_text(json.dumps(err_payload, indent=2), encoding="utf-8")
        (root / "logs" / f"oclw_bot_{ts}.log").write_text(f"ERROR: {e}\n", encoding="utf-8")
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "metrics.json").write_text(json.dumps(err_payload, indent=2), encoding="utf-8")
        return 1


if __name__ == "__main__":
    sys.exit(main())
