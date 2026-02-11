#!/usr/bin/env python3
"""
Apply a Claude/OpenClaw decision to the config YAML.

Reads a JSON decision (from file or stdin), validates changes against
allowed_knobs from llm_input.json, applies to config, and optionally
re-runs make_report.py to verify.

Usage:
  python scripts/apply_changes.py decision.json
  python scripts/apply_changes.py decision.json --config configs/xauusd.yaml
  python scripts/apply_changes.py decision.json --dry-run
  echo '{"decision":"ACCEPT"}' | python scripts/apply_changes.py -
"""
import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import yaml  # pyyaml (in project dependencies)

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _set_nested(cfg: dict, dotpath: str, value) -> None:
    """Set a value in a nested dict using dot notation: 'strategy.tp_r' -> cfg['strategy']['tp_r']."""
    keys = dotpath.split(".")
    d = cfg
    for k in keys[:-1]:
        if k not in d or not isinstance(d[k], dict):
            d[k] = {}
        d = d[k]
    d[keys[-1]] = value


def _get_nested(cfg: dict, dotpath: str, default=None):
    """Get a value from a nested dict using dot notation."""
    keys = dotpath.split(".")
    d = cfg
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def validate_changes(changes: list[dict], allowed_knobs: list[dict]) -> list[str]:
    """Validate proposed changes against allowed knobs. Returns list of error strings."""
    errors = []
    knob_map = {k["path"]: k for k in allowed_knobs}

    for change in changes:
        path = change.get("path")
        to_val = change.get("to")

        if path not in knob_map:
            errors.append(f"REJECTED: '{path}' is not in allowed_knobs")
            continue

        knob = knob_map[path]

        # Type check
        if knob.get("type") == "bool":
            if not isinstance(to_val, bool):
                errors.append(f"REJECTED: '{path}' must be bool, got {type(to_val).__name__}")
            continue

        # Range check
        if isinstance(to_val, (int, float)):
            lo = knob.get("min")
            hi = knob.get("max")
            if lo is not None and to_val < lo:
                errors.append(f"REJECTED: '{path}' value {to_val} below min {lo}")
            if hi is not None and to_val > hi:
                errors.append(f"REJECTED: '{path}' value {to_val} above max {hi}")

    return errors


def apply_changes_to_config(config_path: Path, changes: list[dict]) -> dict:
    """Load YAML config, apply changes, return modified config dict."""
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg = deepcopy(cfg)
    for change in changes:
        path = change["path"]
        to_val = change["to"]
        _set_nested(cfg, path, to_val)

    return cfg


def write_yaml(config_path: Path, cfg: dict) -> None:
    """Write config dict back to YAML."""
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply Claude decision to config")
    ap.add_argument("decision_file", help="Path to decision JSON, or '-' for stdin")
    ap.add_argument("--config", "-c", default="configs/xauusd.yaml", help="Config YAML to modify")
    ap.add_argument("--dry-run", action="store_true", help="Validate only, don't write")
    ap.add_argument("--re-run", action="store_true", help="Re-run make_report.py after applying")
    args = ap.parse_args()

    # Load decision
    if args.decision_file == "-":
        decision = json.load(sys.stdin)
    else:
        decision = _load_json(Path(args.decision_file))

    decision_type = decision.get("decision", "").upper()
    print(f"[apply_changes] Decision: {decision_type}")

    # Handle non-change decisions
    if decision_type == "ACCEPT":
        print("[apply_changes] ACCEPT: no changes needed, current config is good.")
        return
    if decision_type == "REJECT":
        print(f"[apply_changes] REJECT: {decision.get('notes', 'no notes')}")
        return
    if decision_type == "STOP":
        print(f"[apply_changes] STOP: {decision.get('notes', 'cooldown active')}")
        return
    if decision_type != "PROPOSE_CHANGE":
        print(f"[apply_changes] ERROR: unknown decision '{decision_type}'", file=sys.stderr)
        sys.exit(1)

    changes = decision.get("changes", [])
    if not changes:
        print("[apply_changes] PROPOSE_CHANGE but no changes listed.")
        return

    # Load llm_input for allowed knobs
    llm_input_path = ROOT / "reports" / "latest" / "llm_input.json"
    if llm_input_path.exists():
        llm_input = _load_json(llm_input_path)
        allowed_knobs = llm_input.get("allowed_knobs", [])
    else:
        print("[apply_changes] WARNING: llm_input.json not found, skipping knob validation")
        allowed_knobs = []

    # Validate
    if allowed_knobs:
        errors = validate_changes(changes, allowed_knobs)
        if errors:
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            print("[apply_changes] ABORTED: validation failed", file=sys.stderr)
            sys.exit(1)

    # Show changes
    config_path = ROOT / args.config
    print(f"[apply_changes] Applying {len(changes)} change(s) to {config_path}:")
    for c in changes:
        print(f"  {c['path']}: {c.get('from', '?')} -> {c['to']}")

    if args.dry_run:
        print("[apply_changes] DRY RUN: no files modified.")
        return

    # Apply
    new_cfg = apply_changes_to_config(config_path, changes)
    write_yaml(config_path, new_cfg)
    print(f"[apply_changes] Config updated: {config_path}")

    # Log the decision
    log_dir = ROOT / "logs" / "json"
    log_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    decision_log = {
        "timestamp": ts,
        "decision": decision_type,
        "changes": changes,
        "reason_codes": decision.get("reason_codes", []),
        "notes": decision.get("notes", ""),
    }
    log_path = log_dir / f"decision_{ts}.json"
    log_path.write_text(json.dumps(decision_log, indent=2), encoding="utf-8")
    print(f"[apply_changes] Decision logged: {log_path}")

    # Re-run
    if args.re_run:
        import subprocess
        print("[apply_changes] Re-running make_report.py...")
        r = subprocess.run(
            [sys.executable, "scripts/make_report.py", "--config", args.config],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        print(r.stdout)
        if r.returncode != 0:
            print(f"[apply_changes] WARNING: make_report.py exited with code {r.returncode}")
            print(r.stderr)


if __name__ == "__main__":
    main()
