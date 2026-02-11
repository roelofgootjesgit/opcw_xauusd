#!/usr/bin/env python3
"""
Aggregeer alle run-JSONs (logs/json/run_*.json) tot één ML-dataset.

Leest run-context (run_id, days, timeframes, symbol) + settings (geflattent) + kpis,
schrijft één rij per run naar data/ml/runs.csv (en optioneel runs.parquet).

Gebruik:
  python scripts/build_ml_dataset.py
  python scripts/build_ml_dataset.py --out data/ml/runs.csv
  python scripts/build_ml_dataset.py --parquet
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Default paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGS_JSON_DIR = PROJECT_ROOT / "logs" / "json"
DEFAULT_OUT_CSV = PROJECT_ROOT / "data" / "ml" / "runs.csv"
DEFAULT_OUT_PARQUET = PROJECT_ROOT / "data" / "ml" / "runs.parquet"


def _flatten_dict(obj: Any, prefix: str = "") -> Dict[str, Any]:
    """Flatten nested dict to one level; keys become prefix_key_subkey. Lists -> pipe-separated string."""
    if obj is None:
        return {prefix.rstrip("_"): None} if prefix else {}
    if not isinstance(obj, dict):
        return {prefix.rstrip("_"): obj} if prefix else {}
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        key = f"{prefix}{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_dict(v, prefix=f"{key}_"))
        elif isinstance(v, list):
            out[key] = "|".join(str(x) for x in v) if v else ""
        else:
            out[key] = v
    return out


def _row_from_run(data: Dict[str, Any]) -> Dict[str, Any]:
    """Build one flat row: run context + flattened settings + kpis + tests."""
    row: Dict[str, Any] = {
        "run_id": data.get("run_id"),
        "config_path": data.get("config_path") or data.get("config"),
        "days": data.get("days"),
        "symbol": data.get("symbol"),
        "report_run": data.get("report_run"),
    }
    # timeframes: keep as string for CSV (e.g. "15m|1h")
    tf = data.get("timeframes")
    if isinstance(tf, list):
        row["timeframes"] = "|".join(str(x) for x in tf)
    else:
        row["timeframes"] = tf

    # Flatten settings if present (older run JSONs may not have it)
    settings = data.get("settings") or {}
    for k, v in _flatten_dict(settings, prefix="setting_").items():
        row[k] = v

    # KPIs as columns
    kpis = data.get("kpis") or {}
    for k, v in kpis.items():
        row[f"kpi_{k}"] = v

    # Tests
    tests = data.get("tests") or {}
    row["tests_passed"] = tests.get("passed")
    row["tests_failed"] = tests.get("failed")

    return row


def collect_run_jsons(logs_json_dir: Path) -> List[Path]:
    """Return sorted paths to run_*.json files."""
    if not logs_json_dir.exists():
        return []
    files = sorted(logs_json_dir.glob("run_*.json"))
    return files


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build ML dataset from logs/json/run_*.json (settings + KPIs, one row per run)"
    )
    ap.add_argument(
        "--input", "-i",
        default=str(LOGS_JSON_DIR),
        help="Directory with run_*.json files (default: logs/json)",
    )
    ap.add_argument(
        "--out", "-o",
        default=str(DEFAULT_OUT_CSV),
        help="Output CSV path (default: data/ml/runs.csv)",
    )
    ap.add_argument(
        "--parquet", "-p",
        action="store_true",
        help="Also write data/ml/runs.parquet",
    )
    args = ap.parse_args()

    input_dir = Path(args.input)
    if not input_dir.is_absolute():
        input_dir = PROJECT_ROOT / input_dir

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = PROJECT_ROOT / out_path

    files = collect_run_jsons(input_dir)
    if not files:
        print(f"[build_ml_dataset] Geen run_*.json gevonden in {input_dir}", file=sys.stderr)
        return 1

    rows: List[Dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append(_row_from_run(data))
        except Exception as e:
            print(f"[build_ml_dataset] Fout bij lezen {path}: {e}", file=sys.stderr)

    if not rows:
        print("[build_ml_dataset] Geen geldige runs om te schrijven.", file=sys.stderr)
        return 1

    # Normalise columns: union of all keys, consistent order (run context, setting_*, kpi_*, tests_*)
    all_keys: List[str] = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                all_keys.append(k)
    # Prefer a stable order: run_id, config_path, days, timeframes, symbol, report_run, setting_*, kpi_*, tests_*
    def order_key(name: str) -> tuple:
        if name in ("run_id", "config_path", "days", "timeframes", "symbol", "report_run"):
            return (0, name)
        if name.startswith("setting_"):
            return (1, name)
        if name.startswith("kpi_"):
            return (2, name)
        if name.startswith("tests_"):
            return (3, name)
        return (4, name)
    all_keys.sort(key=order_key)

    # Build table (fill missing with None)
    table = []
    for r in rows:
        table.append([r.get(k) for k in all_keys])

    # Write CSV with pandas if available, else manual
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
        df = pd.DataFrame(table, columns=all_keys)
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"[build_ml_dataset] {len(rows)} runs -> {out_path}")
        if args.parquet:
            parquet_path = out_path.parent / (out_path.stem + ".parquet")
            try:
                df.to_parquet(parquet_path, index=False)
                print(f"[build_ml_dataset] Parquet -> {parquet_path}")
            except Exception as e:
                print(f"[build_ml_dataset] Parquet schrijven mislukt (pip install pyarrow?): {e}", file=sys.stderr)
    except ImportError:
        import csv
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(all_keys)
            w.writerows(table)
        print(f"[build_ml_dataset] {len(rows)} runs -> {out_path} (geen pandas, CSV alleen)")
        if args.parquet:
            print("[build_ml_dataset] --parquet genegeerd (pandas nodig)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
