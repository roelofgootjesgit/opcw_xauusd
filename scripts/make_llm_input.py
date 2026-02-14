#!/usr/bin/env python3
"""
Generate a compact LLM input payload for OpenClaw/Claude.

Reads metrics.json, baseline.json, current config, and recent runs.
Outputs reports/latest/llm_input.json (< 3 KB) — the ONLY file Claude needs.

Usage:
  python scripts/make_llm_input.py
  python scripts/make_llm_input.py --config configs/xauusd.yaml
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _round_val(v, decimals=2):
    if isinstance(v, float):
        return round(v, decimals)
    return v


def _compute_diff(current: dict, baseline: dict) -> dict:
    """Compute delta between current and baseline KPIs."""
    diff = {}
    for key in current:
        cur = current.get(key, 0)
        base = baseline.get(key, 0)
        if isinstance(cur, (int, float)) and isinstance(base, (int, float)):
            delta = cur - base
            diff[f"delta_{key}"] = _round_val(delta)
    return diff


def _check_guardrails(current: dict, baseline: dict) -> list[str]:
    """Return list of guardrail flag strings."""
    flags = []
    cur = current
    base = baseline

    # No trades
    if cur.get("trade_count", 0) == 0:
        flags.append("NO_TRADES")

    # Max drawdown worse (more negative = worse)
    cur_dd = cur.get("max_drawdown", 0)
    base_dd = base.get("max_drawdown", 0)
    if base_dd != 0 and cur_dd < base_dd * 1.1:  # 10% margin
        flags.append("DD_WORSE")

    # Profit factor below minimum
    cur_pf = cur.get("profit_factor", 0)
    if cur_pf < 1.0:
        flags.append("PF_BELOW_1")
    base_pf = base.get("profit_factor", 0)
    if base_pf > 0 and cur_pf < base_pf * 0.9:
        flags.append("PF_REGRESSION")

    # Winrate dropped > 2%
    cur_wr = cur.get("winrate", 0)
    base_wr = base.get("winrate", 0)
    if base_wr > 0 and (base_wr - cur_wr) > 0.02:
        flags.append("WINRATE_DROP")

    # Trade count explosion > 20%
    cur_tc = cur.get("trade_count", 0)
    base_tc = base.get("trade_count", 0)
    if base_tc > 0 and cur_tc > base_tc * 1.2:
        flags.append("OVERTRADING")

    return flags


def _get_allowed_knobs(config: dict) -> list[dict]:
    """Extract current values for tunable knobs from config, with min/max from config_space."""
    try:
        from src.trader.ml.config_space import get_default_config_space
        space = get_default_config_space()
    except ImportError:
        space = {}

    knobs = []

    # Backtest knobs
    bt = config.get("backtest", {})
    bt_space = space.get("backtest", {})
    for key in ("tp_r", "sl_r"):
        spec = bt_space.get(key, {})
        knobs.append({
            "path": f"backtest.{key}",
            "current": bt.get(key),
            "min": spec.get("min"),
            "max": spec.get("max"),
        })

    # Strategy knobs
    strat = config.get("strategy", {})
    strat_space = space.get("strategy", {})
    for module_name in ("liquidity_sweep", "displacement", "fair_value_gaps", "market_structure_shift"):
        module_cfg = strat.get(module_name, {})
        module_space = strat_space.get(module_name, {})
        if isinstance(module_cfg, dict):
            for param, value in module_cfg.items():
                spec = module_space.get(param, {})
                knobs.append({
                    "path": f"strategy.{module_name}.{param}",
                    "current": value,
                    "min": spec.get("min"),
                    "max": spec.get("max"),
                })

    # Boolean knobs
    for bool_key in ("require_structure", "structure_use_h1_gate", "entry_require_sweep_displacement_fvg"):
        if bool_key in strat:
            knobs.append({
                "path": f"strategy.{bool_key}",
                "current": strat[bool_key],
                "type": "bool",
            })

    # Integer knobs
    for int_key in ("entry_sweep_disp_fvg_lookback_bars", "entry_sweep_disp_fvg_min_count"):
        if int_key in strat:
            knobs.append({
                "path": f"strategy.{int_key}",
                "current": strat[int_key],
                "min": 1,
                "max": 10,
            })

    return knobs


def _get_regime_knobs(config: dict) -> list[dict]:
    """Extract tunable knobs for regime-specific profiles."""
    regime_profiles = config.get("regime_profiles", {})
    knobs = []
    for regime_name, profile in regime_profiles.items():
        if not isinstance(profile, dict):
            continue
        for param, value in profile.items():
            if isinstance(value, (int, float, bool)):
                knob = {
                    "path": f"regime_profiles.{regime_name}.{param}",
                    "current": value,
                }
                # Set reasonable min/max for known params
                if param == "tp_r":
                    knob["min"] = 1.0
                    knob["max"] = 5.0
                elif param == "sl_r":
                    knob["min"] = 0.5
                    knob["max"] = 3.0
                elif param == "position_size_multiplier":
                    knob["min"] = 0.25
                    knob["max"] = 2.0
                elif param == "max_trades_per_session":
                    knob["min"] = 1
                    knob["max"] = 5
                elif param == "entry_sweep_disp_fvg_min_count":
                    knob["min"] = 1
                    knob["max"] = 3
                elif isinstance(value, bool):
                    knob["type"] = "bool"
                knobs.append(knob)
    return knobs


def _check_cooldown(json_dir: Path, max_streak: int = 3) -> dict:
    """Check last N runs for repeated failures / 0 trades."""
    json_files = sorted(json_dir.glob("run_*.json"), reverse=True)[:max_streak]
    if len(json_files) < max_streak:
        return {"cooldown": False}

    zero_trades_streak = 0
    for f in json_files:
        data = _load_json(f)
        kpis = data.get("kpis", {})
        if kpis.get("trade_count", 0) == 0:
            zero_trades_streak += 1

    if zero_trades_streak >= max_streak:
        return {
            "cooldown": True,
            "reason": f"{max_streak}x consecutive 0 trades — manual analysis needed, stop LLM calls",
        }
    return {"cooldown": False}


def _count_runs_today(json_dir: Path) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sum(1 for f in json_dir.glob(f"run_{today}*.json"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate compact LLM input")
    ap.add_argument("--config", "-c", default=None, help="Config YAML path")
    args = ap.parse_args()

    from src.trader.config import load_config

    config = load_config(args.config)
    latest_dir = ROOT / "reports" / "latest"
    history_dir = ROOT / "reports" / "history"
    json_dir = ROOT / "logs" / "json"

    # Load metrics and baseline
    metrics = _load_json(latest_dir / "metrics.json")
    baseline = _load_json(history_dir / "baseline.json")

    cur_kpis = metrics.get("kpis", {})
    base_kpis = baseline.get("kpis", {})

    # Round KPIs for compact output
    cur_kpis_rounded = {k: _round_val(v) for k, v in cur_kpis.items()}

    # Compute diff and guardrails
    diff = _compute_diff(cur_kpis, base_kpis)
    flags = _check_guardrails(cur_kpis, base_kpis)

    # Check cooldown
    cooldown = _check_cooldown(json_dir)

    # Get allowed knobs
    knobs = _get_allowed_knobs(config)

    # Test status
    tests = metrics.get("tests", {})
    tests_pass = tests.get("failed", 0) == 0

    # Regime breakdown (if available)
    regime_breakdown = metrics.get("by_regime", {})
    regime_rounded = {}
    for regime_name, regime_kpis in regime_breakdown.items():
        regime_rounded[regime_name] = {k: _round_val(v) for k, v in regime_kpis.items()}

    # Direction breakdown (if available)
    direction_breakdown = metrics.get("by_direction", {})
    direction_rounded = {}
    for dir_name, dir_kpis in direction_breakdown.items():
        direction_rounded[dir_name] = {k: _round_val(v) for k, v in dir_kpis.items()}

    # Per-regime allowed knobs
    regime_knobs = _get_regime_knobs(config)

    # Build payload
    payload = {
        "run_id": metrics.get("run_id", "unknown"),
        "git_commit": metrics.get("git_commit", "unknown"),
        "status": "PASS" if tests_pass and not flags else "FAIL",
        "tests": {
            "passed": tests.get("passed", 0),
            "failed": tests.get("failed", 0),
        },
        "kpis": cur_kpis_rounded,
        "by_direction": direction_rounded,
        "by_regime": regime_rounded,
        "baseline_diff": diff,
        "guardrail_flags": flags,
        "allowed_knobs": knobs,
        "regime_knobs": regime_knobs,
        "cooldown": cooldown,
        "runs_today": _count_runs_today(json_dir),
        "max_runs_per_day": 10,
        "_instructions": (
            "You are the Improver-Agent. Respond ONLY with the JSON decision format. "
            "Do NOT read any other files. Do NOT explore the codebase. "
            "If cooldown is true, respond with decision=STOP. "
            "If guardrail_flags is empty and status=PASS, respond with decision=ACCEPT. "
            "If you propose changes, use ONLY paths from allowed_knobs or regime_knobs. "
            "You can now tune per-regime parameters via regime_knobs (e.g. regime_profiles.trending.tp_r)."
        ),
    }

    # Write output
    latest_dir.mkdir(parents=True, exist_ok=True)
    out_path = latest_dir / "llm_input.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"[make_llm_input] Written: {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
