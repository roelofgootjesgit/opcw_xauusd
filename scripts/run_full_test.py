#!/usr/bin/env python3
"""
Standaard script: alles voor een volle strategietest op Yahoo-data.

Doet in volgorde:
  1. Check omgeving (venv, yfinance)
  2. Fetch market data (Yahoo) voor de opgegeven periode
  3. Backtest op dezelfde periode
  4. Optioneel: pytest + report (zoals make_report.py)

Log output gaat naar console én naar het logbestand uit config (standaard logs/oclw_bot.log).

Gebruik:
  python scripts/run_full_test.py
  python scripts/run_full_test.py --days 30
  python scripts/run_full_test.py --days 30 --config configs/xauusd.yaml
  python scripts/run_full_test.py --days 30 --report
  python scripts/run_full_test.py --skip-fetch   # alleen backtest op bestaande data
"""
import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


def project_root() -> Path:
    root = Path(__file__).resolve().parents[1]
    return root


def _ensure_deps_and_venv() -> None:
    """If yaml is missing, try to re-exec with project .venv Python; else exit with clear message."""
    try:
        import yaml  # noqa: F401
        return
    except ImportError:
        pass
    root = project_root()
    is_windows = os.name == "nt"
    venv_python = root / ".venv" / ("Scripts" if is_windows else "bin") / ("python.exe" if is_windows else "python")
    # Only re-exec if we're not already running from this project's venv (avoid loop when venv is empty)
    try:
        exe_path = Path(sys.executable).resolve()
        venv_root = (root / ".venv").resolve()
        same_venv = venv_root in exe_path.parents or exe_path == venv_python.resolve()
    except Exception:
        same_venv = False
    if venv_python.exists() and not same_venv:
        os.chdir(root)
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)
        return  # unreachable
    print("Ontbrekende dependencies. Run eerst (in deze map):", file=sys.stderr)
    print("  python scripts/setup_venv.py", file=sys.stderr)
    print("Daarna venv activeren en opnieuw:", file=sys.stderr)
    print("  .\\.venv\\Scripts\\Activate.ps1   # Windows", file=sys.stderr)
    print("  python scripts/run_full_test.py", file=sys.stderr)
    sys.exit(1)


def setup_logging_from_config(root: Path, config_path: str) -> Tuple[logging.Logger, Optional[Path]]:
    """Load config and setup logging (console + file). Returns (logger, run_log_path for this run)."""
    sys.path.insert(0, str(root))
    from src.trader.config import load_config
    from src.trader.logging_config import setup_logging as _setup, log_path_with_timestamp
    cfg = load_config(config_path)
    run_log_path = None
    file_path = cfg.get("logging", {}).get("file_path") or cfg.get("logging", {}).get("file")
    if file_path:
        # Altijd absoluut pad t.o.v. project root, zodat het logbestand altijd in de projectmap staat
        path = (root / log_path_with_timestamp(file_path)).resolve()
        os.environ["OCLW_LOG_FILE"] = str(path)
        run_log_path = path
    _setup(cfg)
    return logging.getLogger("run_full_test"), run_log_path


def in_venv() -> bool:
    return getattr(sys, "prefix", "") != getattr(sys, "base_prefix", sys.prefix) or hasattr(
        sys, "real_prefix"
    )


def check_env(log: logging.Logger) -> bool:
    ok = True
    if not in_venv():
        log.warning(
            "venv lijkt niet actief. Activeren: .venv\\Scripts\\Activate.ps1 (Windows) of source .venv/bin/activate (Linux)"
        )
    try:
        import yfinance  # noqa: F401
    except ImportError:
        log.error("yfinance niet gevonden. Installeer: pip install -e \".[yfinance]\"")
        ok = False
    return ok


def write_run_json(root: Path, run_log_path: Path | None, args: argparse.Namespace, log: logging.Logger) -> None:
    """Write per-run JSON (ML-friendly) next to the .log file. .log = human, .json = ML."""
    if not run_log_path:
        return
    run_dir = run_log_path.parent
    # JSONs in submap logs/json/
    json_dir = run_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    # Zelfde timestamp als log: oclw_bot_2026-02-09_21-08-49.log -> json/run_2026-02-09_21-08-49.json
    parts = run_log_path.stem.split("_")
    time_part = "_".join(parts[2:]) if len(parts) >= 3 else datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    json_path = json_dir / f"run_{time_part}.json"

    payload = {
        "run_id": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": args.days,
        "config": args.config,
        "report_run": args.report,
    }
    # Prefer metrics from report if available
    metrics_file = root / "reports" / "latest" / "metrics.json"
    if metrics_file.exists():
        try:
            data = json.loads(metrics_file.read_text(encoding="utf-8"))
            payload["kpis"] = data.get("kpis", {})
            payload["tests"] = data.get("tests", {})
            payload["run_id"] = data.get("run_id", payload["run_id"])
        except Exception as e:
            log.warning("Could not read metrics.json for run JSON: %s", e)
    else:
        # Run backtest in-process to get KPIs for this run
        try:
            sys.path.insert(0, str(root))
            from src.trader.config import load_config
            from src.trader.backtest.engine import run_backtest
            from src.trader.backtest.metrics import compute_metrics
            cfg = load_config(args.config)
            cfg.setdefault("backtest", {})["default_period_days"] = args.days
            trades = run_backtest(cfg)
            payload["kpis"] = dict(compute_metrics(trades))
            payload["tests"] = {}
        except Exception as e:
            log.warning("Could not compute metrics for run JSON: %s", e)
            payload["kpis"] = {}
            payload["tests"] = {}

    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log.info("Run JSON (ML): %s", json_path)


def run(cmd: list[str], cwd: Path, label: str, log: logging.Logger) -> bool:
    log.info("--- %s ---", label)
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        log.error("Fout bij: %s (exit %d)", label, r.returncode)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Volledige strategietest: fetch + backtest (+ optioneel report)"
    )
    ap.add_argument(
        "--days", "-d",
        type=int,
        default=30,
        help="Aantal dagen data en backtest-periode (default: 30 = 1 maand)",
    )
    ap.add_argument(
        "--config", "-c",
        default="configs/xauusd.yaml",
        help="Config YAML (default: configs/xauusd.yaml)",
    )
    ap.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Geen fetch; alleen backtest op bestaande cache",
    )
    ap.add_argument(
        "--report", "-r",
        action="store_true",
        help="Na backtest ook pytest + make_report uitvoeren",
    )
    args = ap.parse_args()

    # Use project .venv if current Python is missing deps (e.g. run without activating venv)
    _ensure_deps_and_venv()

    root = project_root()
    config_path = args.config
    if not (root / config_path).exists():
        config_path = "configs/default.yaml"
    if not (root / config_path).exists():
        print(f"[run_full_test] Config niet gevonden: {args.config}")
        return 1

    log, run_log_path = setup_logging_from_config(root, config_path)
    if run_log_path:
        log.info("Logbestand: %s", run_log_path)
    if root != Path.cwd():
        log.info("Project root: %s", root)
    log.info("run_full_test start (days=%s config=%s)", args.days, config_path)

    if not check_env(log):
        return 1

    # 1) Fetch (tenzij --skip-fetch)
    if not args.skip_fetch:
        if not run(
            [sys.executable, "-m", "src.trader.app", "--config", config_path, "fetch", "--days", str(args.days)],
            root,
            f"Fetch {args.days} dagen Yahoo (config: {config_path})",
            log,
        ):
            return 1
    else:
        log.info("Fetch overgeslagen (--skip-fetch)")

    # 2) Backtest
    if not run(
        [sys.executable, "-m", "src.trader.app", "--config", config_path, "backtest", "--days", str(args.days)],
        root,
        f"Backtest {args.days} dagen",
        log,
    ):
        return 1

    # 3) Optioneel: report (pytest + make_report)
    if args.report:
        report_cmd = [sys.executable, str(root / "scripts" / "make_report.py"), "--config", config_path, "--days", str(args.days)]
        if not run(
            report_cmd,
            root,
            "Tests + report (make_report.py)",
            log,
        ):
            return 1
        log.info("Klaar. Zie reports/latest/REPORT.md en metrics.json")
    else:
        log.info("Klaar. Voor volledig rapport: python scripts/run_full_test.py --days 30 --report")

    # Per-run JSON voor ML (zelfde map als .log)
    write_run_json(root, run_log_path, args, log)

    return 0


if __name__ == "__main__":
    sys.exit(main())
