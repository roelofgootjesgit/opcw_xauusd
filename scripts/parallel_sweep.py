"""
Parallel parameter sweep: run multiple config variants simultaneously.

Computes regime detection ONCE, then runs all config variants in parallel
using multiprocessing. Produces a comparison table (stdout + JSON).

Usage:
    python scripts/parallel_sweep.py                          # default grid
    python scripts/parallel_sweep.py --days 365               # 1 year
    python scripts/parallel_sweep.py --config configs/xauusd.yaml --workers 4
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trader.backtest.engine import run_backtest
from src.trader.backtest.metrics import compute_metrics
from src.trader.io.parquet_loader import load_parquet
from src.trader.strategy_modules.regime.detector import RegimeDetector

logger = logging.getLogger("parallel_sweep")

# ─────────────────────────────────────────────────────
# Default sweep grid — each entry is a set of overrides
# on top of the base config.  Dot-notation paths like
# "backtest.tp_r" are expanded automatically.
# ─────────────────────────────────────────────────────
DEFAULT_GRID: List[Dict[str, Any]] = [
    {"label": "baseline",       "changes": {}},
    {"label": "tp_r_2.0",       "changes": {"backtest.tp_r": 2.0}},
    {"label": "tp_r_3.0",       "changes": {"backtest.tp_r": 3.0}},
    {"label": "body_70",        "changes": {"strategy.displacement.min_body_pct": 70}},
    {"label": "move_1.0",       "changes": {"strategy.displacement.min_move_pct": 1.0}},
    {"label": "sweep_0.12",     "changes": {"strategy.liquidity_sweep.sweep_threshold_pct": 0.12}},
    {"label": "lookback_7",     "changes": {"strategy.entry_sweep_disp_fvg_lookback_bars": 7}},
]


def _set_nested(d: dict, dotpath: str, value: Any) -> None:
    """Set a value in a nested dict using dot-separated path."""
    keys = dotpath.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _apply_overrides(base_cfg: dict, changes: dict) -> dict:
    """Deep-copy base config and apply dot-path overrides."""
    cfg = copy.deepcopy(base_cfg)
    for dotpath, value in changes.items():
        _set_nested(cfg, dotpath, value)
    return cfg


def _compute_regime_once(
    base_path: Path,
    symbol: str,
    period_days: int,
) -> Optional[pd.Series]:
    """
    Compute regime detection once for the full data range.
    Returns regime Series aligned to 15m data index.
    """
    end = datetime.now()
    start = end - timedelta(days=period_days)

    data_15m = load_parquet(base_path, symbol, "15m", start=start, end=end)
    if data_15m.empty or len(data_15m) < 50:
        logger.warning("No 15m data for regime pre-computation")
        return None
    data_15m = data_15m.sort_index()

    data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
    if not data_1h.empty:
        data_1h = data_1h.sort_index()

    detector = RegimeDetector()
    regime = detector.classify(data_15m, data_1h if not data_1h.empty else None)
    logger.info("Regime pre-computed: %d bars. Distribution: %s",
                len(regime), regime.value_counts().to_dict())
    return regime


def _run_single_variant(
    label: str,
    cfg: dict,
    regime_values: Optional[list],
    regime_index: Optional[list],
) -> dict:
    """
    Run a single backtest variant.  Executed in a worker process.

    regime_values/regime_index are passed as plain lists (picklable)
    and reconstructed into a pd.Series inside the worker.
    """
    # Reconstruct regime Series from lists (avoids pickle issues)
    precomputed = None
    if regime_values is not None and regime_index is not None:
        precomputed = pd.Series(regime_values, index=pd.DatetimeIndex(regime_index))

    t0 = time.perf_counter()
    trades = run_backtest(cfg, precomputed_regime=precomputed)
    elapsed = time.perf_counter() - t0

    metrics = compute_metrics(trades)
    metrics["label"] = label
    metrics["elapsed_sec"] = round(elapsed, 1)
    return metrics


def _print_table(results: List[dict]) -> None:
    """Pretty-print comparison table to stdout."""
    cols = ["label", "trade_count", "win_rate", "profit_factor",
            "max_drawdown", "expectancy_r", "net_pnl", "elapsed_sec"]
    headers = ["Config", "Trades", "WR%", "PF", "MaxDD(R)", "Exp(R)", "NetPnL$", "Time(s)"]

    # Column widths
    widths = [max(len(h), 14) for h in headers]
    widths[0] = max(widths[0], max(len(r.get("label", "")) for r in results) + 2)

    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep_line = "-+-".join("-" * w for w in widths)

    print()
    print(header_line)
    print(sep_line)

    # Sort by profit_factor descending
    sorted_results = sorted(results, key=lambda r: r.get("profit_factor", 0), reverse=True)

    for r in sorted_results:
        vals = [
            r.get("label", "?"),
            str(r.get("trade_count", 0)),
            f"{r.get('win_rate', 0):.1f}",
            f"{r.get('profit_factor', 0):.2f}",
            f"{r.get('max_drawdown', 0):.1f}",
            f"{r.get('expectancy_r', 0):.2f}",
            f"{r.get('net_pnl', 0):.2f}",
            f"{r.get('elapsed_sec', 0):.1f}",
        ]
        print(" | ".join(v.ljust(w) for v, w in zip(vals, widths)))

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Parallel parameter sweep")
    parser.add_argument("--config", default="configs/xauusd.yaml",
                        help="Base config YAML (default: configs/xauusd.yaml)")
    parser.add_argument("--days", type=int, default=None,
                        help="Override backtest period (days)")
    parser.add_argument("--workers", type=int, default=None,
                        help="Max parallel workers (default: CPU count)")
    parser.add_argument("--grid", default=None,
                        help="JSON file with custom sweep grid")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-trade logging from workers")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Always show sweep-level messages
    logger.setLevel(logging.INFO)

    # Load base config
    config_path = ROOT / args.config
    with open(config_path, encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f)

    if args.days:
        base_cfg.setdefault("backtest", {})["default_period_days"] = args.days

    # Load sweep grid
    if args.grid:
        with open(args.grid, encoding="utf-8") as f:
            grid = json.load(f)
    else:
        grid = DEFAULT_GRID

    period_days = base_cfg.get("backtest", {}).get("default_period_days", 90)
    symbol = base_cfg.get("symbol", "XAUUSD")
    base_path = Path(base_cfg.get("data", {}).get("base_path", "data/market_cache"))

    logger.info("=== Parallel Sweep: %d configs x %d days ===", len(grid), period_days)

    # ── Step 1: Pre-compute regime (once) ──
    t0 = time.perf_counter()
    regime_series = _compute_regime_once(base_path, symbol, period_days)
    t_regime = time.perf_counter() - t0
    logger.info("Regime computed in %.1fs", t_regime)

    # Convert to picklable lists for worker processes
    regime_values = regime_series.values.tolist() if regime_series is not None else None
    regime_index = regime_series.index.tolist() if regime_series is not None else None

    # ── Step 2: Build config variants ──
    variants = []
    for entry in grid:
        label = entry["label"]
        changes = entry.get("changes", {})
        cfg = _apply_overrides(base_cfg, changes)
        variants.append((label, cfg))

    # ── Step 3: Run in parallel ──
    t0 = time.perf_counter()
    results: List[dict] = []

    max_workers = args.workers or min(len(variants), 6)
    logger.info("Launching %d workers for %d variants...", max_workers, len(variants))

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for label, cfg in variants:
            fut = pool.submit(
                _run_single_variant,
                label, cfg,
                regime_values, regime_index,
            )
            futures[fut] = label

        for fut in as_completed(futures):
            label = futures[fut]
            try:
                metrics = fut.result()
                results.append(metrics)
                logger.info("[%s] done — %d trades, PF=%.2f, WR=%.1f%%",
                            label, metrics.get("trade_count", 0),
                            metrics.get("profit_factor", 0),
                            metrics.get("win_rate", 0))
            except Exception as e:
                logger.error("[%s] FAILED: %s", label, e)
                results.append({"label": label, "error": str(e)})

    t_total = time.perf_counter() - t0
    logger.info("All variants done in %.1fs (regime: %.1fs + backtests: %.1fs)",
                t_regime + t_total, t_regime, t_total)

    # ── Step 4: Output results ──
    _print_table(results)

    # Save JSON
    out_dir = ROOT / "reports" / "latest"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "sweep_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("Results saved: %s", out_file)


if __name__ == "__main__":
    main()
