#!/usr/bin/env python3
"""
Automatic strategy improver: rule-based optimizer loop with optional LLM upgrade.

Runs the full test → reads llm_input.json → decides → applies → repeats.
No LLM credits needed for the default rule-based mode.

Usage:
  python scripts/auto_improve.py                              # 1 iteration, rule-based
  python scripts/auto_improve.py --max-iter 5                 # up to 5 iterations
  python scripts/auto_improve.py --max-iter 3 --days 30       # 30-day backtest
  python scripts/auto_improve.py --use-llm                    # OpenClaw/Anthropic (needs credits)
  python scripts/auto_improve.py --dry-run                    # show decisions without applying

Architecture (designed for ML extension):
  - RuleBasedDecider: deterministic heuristics (current)
  - LLMDecider: OpenClaw/Anthropic API (--use-llm flag)
  - Future: MLDecider using Thompson Sampling / historical performance data
"""
import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - auto_improve - %(levelname)s - %(message)s",
)
log = logging.getLogger("auto_improve")


# ---------------------------------------------------------------------------
# Decision interface (Protocol for future ML/LLM deciders)
# ---------------------------------------------------------------------------

class Decider(Protocol):
    """Interface for decision-making. Implement this for ML/LLM extensions."""

    def decide(self, llm_input: dict) -> dict:
        """Return a decision dict: {decision, reason_codes, changes, notes}."""
        ...


# ---------------------------------------------------------------------------
# Rule-based decider (no LLM needed)
# ---------------------------------------------------------------------------

# Step sizes for parameter changes (conservative)
STEP_SIZES = {
    "backtest.tp_r": 0.5,
    "backtest.sl_r": 0.25,
    "strategy.liquidity_sweep.lookback_candles": 5,
    "strategy.liquidity_sweep.sweep_threshold_pct": 0.03,
    "strategy.liquidity_sweep.reversal_candles": 1,
    "strategy.displacement.min_body_pct": 5,
    "strategy.displacement.min_candles": 1,
    "strategy.displacement.min_move_pct": 0.25,
    "strategy.fair_value_gaps.min_gap_pct": 0.05,
    "strategy.fair_value_gaps.validity_candles": 10,
    "strategy.market_structure_shift.swing_lookback": 1,
    "strategy.market_structure_shift.break_threshold_pct": 0.05,
    "strategy.entry_sweep_disp_fvg_lookback_bars": 1,
    "strategy.entry_sweep_disp_fvg_min_count": 1,
}

# Which knobs to try per flag, in priority order
# (direction: "up" = increase value, "down" = decrease, "on"/"off" for bools)
FLAG_ACTIONS = {
    "PF_BELOW_1": [
        ("backtest.tp_r", "up"),
        ("strategy.structure_use_h1_gate", "on"),
        ("strategy.displacement.min_move_pct", "up"),
        ("strategy.market_structure_shift.break_threshold_pct", "down"),
    ],
    "NO_TRADES": [
        ("strategy.liquidity_sweep.sweep_threshold_pct", "down"),
        ("strategy.displacement.min_move_pct", "down"),
        ("strategy.entry_sweep_disp_fvg_min_count", "down"),
        ("strategy.require_structure", "off"),
    ],
    "DD_WORSE": [
        ("strategy.require_structure", "on"),
        ("strategy.structure_use_h1_gate", "on"),
        ("strategy.displacement.min_move_pct", "up"),
        ("backtest.sl_r", "down"),
    ],
    "PF_REGRESSION": [
        # Revert-achtig: conservatiever worden
        ("backtest.tp_r", "up"),
        ("strategy.displacement.min_move_pct", "up"),
    ],
    "WINRATE_DROP": [
        ("backtest.tp_r", "down"),
        ("strategy.displacement.min_move_pct", "down"),
        ("strategy.entry_sweep_disp_fvg_min_count", "down"),
    ],
    "OVERTRADING": [
        ("strategy.displacement.min_move_pct", "up"),
        ("strategy.liquidity_sweep.sweep_threshold_pct", "up"),
        ("strategy.require_structure", "on"),
        ("strategy.structure_use_h1_gate", "on"),
    ],
}


def _knob_map(allowed_knobs: list[dict]) -> dict:
    """Build path -> knob dict from allowed_knobs."""
    return {k["path"]: k for k in allowed_knobs}


def _recent_changes(json_dir: Path, n: int = 3) -> list[dict]:
    """Load last N decision logs to avoid repeating the same change."""
    decision_files = sorted(json_dir.glob("decision_*.json"), reverse=True)[:n]
    changes = []
    for f in decision_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            changes.extend(data.get("changes", []))
        except Exception:
            pass
    return changes


def _already_tried(path: str, direction: str, recent: list[dict]) -> bool:
    """Check if we recently tried the same change direction on the same knob."""
    for c in recent:
        if c.get("path") == path:
            old, new = c.get("from", 0), c.get("to", 0)
            if direction == "up" and new > old:
                return True
            if direction == "down" and new < old:
                return True
            if direction in ("on", "off"):
                return True
    return False


def _propose_change(path: str, direction: str, knobs: dict) -> Optional[dict]:
    """Propose a single parameter change within allowed bounds."""
    knob = knobs.get(path)
    if not knob:
        return None

    current = knob.get("current")
    if current is None:
        return None

    # Boolean knobs
    if knob.get("type") == "bool":
        target = True if direction == "on" else False
        if current == target:
            return None  # already set
        return {"path": path, "from": current, "to": target}

    # Numeric knobs
    step = STEP_SIZES.get(path, 0.1)
    if direction == "up":
        new_val = current + step
    elif direction == "down":
        new_val = current - step
    else:
        return None

    # Respect min/max
    lo = knob.get("min")
    hi = knob.get("max")
    if lo is not None and new_val < lo:
        new_val = lo
    if hi is not None and new_val > hi:
        new_val = hi

    # Don't propose if nothing changes
    if new_val == current:
        return None

    # Keep ints as ints
    if isinstance(current, int):
        new_val = int(round(new_val))

    return {"path": path, "from": current, "to": new_val}


class RuleBasedDecider:
    """Deterministic decision engine following AGENTS.md logic."""

    def decide(self, llm_input: dict) -> dict:
        cooldown = llm_input.get("cooldown", {})
        if cooldown.get("cooldown", False):
            return {
                "decision": "STOP",
                "reason_codes": ["COOLDOWN"],
                "changes": [],
                "notes": cooldown.get("reason", "cooldown active"),
            }

        runs_today = llm_input.get("runs_today", 0)
        max_runs = llm_input.get("max_runs_per_day", 10)
        if runs_today >= max_runs:
            return {
                "decision": "STOP",
                "reason_codes": ["MAX_RUNS"],
                "changes": [],
                "notes": f"runs_today={runs_today} >= max={max_runs}",
            }

        tests = llm_input.get("tests", {})
        if tests.get("failed", 0) > 0:
            return {
                "decision": "REJECT",
                "reason_codes": ["TESTS_FAILING"],
                "changes": [],
                "notes": f"{tests['failed']} test(s) failing, fix before tuning",
            }

        flags = llm_input.get("guardrail_flags", [])
        status = llm_input.get("status", "FAIL")

        if not flags and status == "PASS":
            return {
                "decision": "ACCEPT",
                "reason_codes": ["ALL_GREEN"],
                "changes": [],
                "notes": "",
            }

        # Propose changes based on flags
        knobs = _knob_map(llm_input.get("allowed_knobs", []))
        json_dir = ROOT / "logs" / "json"
        recent = _recent_changes(json_dir)

        changes = []
        reasons = []
        notes_parts = []

        for flag in flags:
            if flag not in FLAG_ACTIONS:
                continue
            reasons.append(flag)
            for path, direction in FLAG_ACTIONS[flag]:
                if len(changes) >= 2:  # max 2 changes per iteration (conservative)
                    break
                # Skip if we recently tried this exact move
                if _already_tried(path, direction, recent):
                    continue
                change = _propose_change(path, direction, knobs)
                if change and not any(c["path"] == change["path"] for c in changes):
                    changes.append(change)
                    notes_parts.append(f"{path}: {change['from']}->{change['to']}")

        if not changes:
            # All options exhausted for these flags
            return {
                "decision": "ACCEPT",
                "reason_codes": flags + ["NO_MORE_MOVES"],
                "changes": [],
                "notes": "Alle knobs voor deze flags al geprobeerd of op limiet",
            }

        return {
            "decision": "PROPOSE_CHANGE",
            "reason_codes": reasons,
            "changes": changes,
            "notes": "; ".join(notes_parts)[:200],
        }


# ---------------------------------------------------------------------------
# LLM decider (OpenClaw / Anthropic — future)
# ---------------------------------------------------------------------------

def _extract_json_decision(text: str) -> Optional[dict]:
    """Extract a JSON decision from LLM response text.

    Handles:
    - Pure JSON response
    - JSON wrapped in ```json ... ``` markdown
    - JSON embedded in explanation text
    - Multiple JSON blocks (takes the one with 'decision' key)
    """
    import re

    text = text.strip()

    # Try 1: direct JSON parse
    try:
        d = json.loads(text)
        if isinstance(d, dict) and "decision" in d:
            return d
    except json.JSONDecodeError:
        pass

    # Try 2: extract from ```json ... ``` block
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if md_match:
        try:
            d = json.loads(md_match.group(1).strip())
            if isinstance(d, dict) and "decision" in d:
                return d
        except json.JSONDecodeError:
            pass

    # Try 3: find first { ... } block that contains "decision"
    brace_matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    for candidate in brace_matches:
        try:
            d = json.loads(candidate)
            if isinstance(d, dict) and "decision" in d:
                return d
        except json.JSONDecodeError:
            continue

    # Try 4: find outermost { ... } with nested braces
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    d = json.loads(text[start : i + 1])
                    if isinstance(d, dict) and "decision" in d:
                        return d
                except json.JSONDecodeError:
                    pass
                start = None

    return None


class LLMDecider:
    """LLM-based decision engine using OpenClaw CLI."""

    def __init__(self, agent: str = "main", timeout: int = 120):
        self.agent = agent
        self.timeout = timeout

    def decide(self, llm_input: dict) -> dict:
        prompt_path = ROOT / "oclw_bot" / "prompts" / "improver.md"
        system_prompt = ""
        if prompt_path.exists():
            system_prompt = prompt_path.read_text(encoding="utf-8") + "\n\n"

        message = system_prompt + "```json\n" + json.dumps(llm_input, indent=2) + "\n```"

        try:
            r = subprocess.run(
                [
                    "openclaw", "agent",
                    "--agent", self.agent,
                    "--message", message,
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=ROOT,
            )
            if r.returncode != 0:
                log.error("OpenClaw agent failed: %s", r.stderr)
                return {"decision": "STOP", "reason_codes": ["LLM_ERROR"], "changes": [], "notes": r.stderr[:200]}

            result = json.loads(r.stdout)
            # Extract text from payloads
            payloads = result.get("result", {}).get("payloads", [])
            text = payloads[0].get("text", "") if payloads else ""

            log.debug("LLM raw response: %s", text[:500])

            # Extract JSON from response — LLM might wrap it in markdown or add explanation
            decision = _extract_json_decision(text)
            if decision:
                return decision

            log.error("Could not extract JSON decision from LLM response: %s", text[:300])
            return {"decision": "STOP", "reason_codes": ["LLM_PARSE_ERROR"], "changes": [], "notes": text[:200]}

        except subprocess.TimeoutExpired:
            return {"decision": "STOP", "reason_codes": ["LLM_TIMEOUT"], "changes": [], "notes": "LLM timeout"}
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            log.error("Failed to parse LLM response: %s", e)
            return {"decision": "STOP", "reason_codes": ["LLM_PARSE_ERROR"], "changes": [], "notes": str(e)[:200]}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_full_test(config: str, days: int) -> bool:
    """Run the full test pipeline. Returns True if successful."""
    cmd = [
        sys.executable, str(ROOT / "scripts" / "run_full_test.py"),
        "--days", str(days),
        "--config", config,
        "--report",
    ]
    log.info("Running: %s", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT, timeout=600)
    return r.returncode == 0


def load_llm_input() -> dict:
    """Load the latest llm_input.json."""
    path = ROOT / "reports" / "latest" / "llm_input.json"
    if not path.exists():
        log.error("llm_input.json not found at %s", path)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def apply_decision(decision: dict, config: str, dry_run: bool = False) -> bool:
    """Save decision and run apply_changes.py. Returns True if successful."""
    decision_path = ROOT / "decision.json"
    decision_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")

    if decision["decision"] != "PROPOSE_CHANGE":
        log.info("Decision: %s — no changes to apply", decision["decision"])
        return True

    cmd = [
        sys.executable, str(ROOT / "scripts" / "apply_changes.py"),
        str(decision_path),
        "--config", config,
    ]
    if dry_run:
        cmd.append("--dry-run")
    else:
        cmd.append("--re-run")

    r = subprocess.run(cmd, cwd=ROOT, timeout=300)
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Automatic strategy improver (rule-based, with optional LLM)"
    )
    ap.add_argument("--max-iter", "-n", type=int, default=1, help="Max iterations (default: 1)")
    ap.add_argument("--days", "-d", type=int, default=30, help="Backtest period in days (default: 30)")
    ap.add_argument("--config", "-c", default="configs/xauusd.yaml", help="Config YAML")
    ap.add_argument("--dry-run", action="store_true", help="Show decisions without applying")
    ap.add_argument("--use-llm", action="store_true", help="Use OpenClaw/Anthropic instead of rules")
    ap.add_argument("--llm-agent", default="main", help="OpenClaw agent id (default: main)")
    ap.add_argument("--skip-first-test", action="store_true",
                     help="Skip first test run (use existing llm_input.json)")
    args = ap.parse_args()

    # Select decider
    if args.use_llm:
        decider: Decider = LLMDecider(agent=args.llm_agent)
        log.info("Using LLM decider (OpenClaw agent: %s)", args.llm_agent)
    else:
        decider = RuleBasedDecider()
        log.info("Using rule-based decider")

    log.info("Starting auto_improve: max_iter=%d, days=%d, config=%s", args.max_iter, args.days, args.config)

    for iteration in range(1, args.max_iter + 1):
        log.info("=" * 60)
        log.info("ITERATION %d/%d", iteration, args.max_iter)
        log.info("=" * 60)

        # Step 1: Run full test (skip first if requested and llm_input exists)
        if iteration == 1 and args.skip_first_test:
            llm_input_path = ROOT / "reports" / "latest" / "llm_input.json"
            if llm_input_path.exists():
                log.info("Skipping first test run (--skip-first-test)")
            else:
                log.info("No existing llm_input.json, running test anyway")
                if not run_full_test(args.config, args.days):
                    log.error("Test run failed, stopping")
                    return 1
        else:
            if not run_full_test(args.config, args.days):
                log.error("Test run failed, stopping")
                return 1

        # Step 2: Read llm_input.json
        llm_input = load_llm_input()
        if not llm_input:
            log.error("Empty llm_input, stopping")
            return 1

        kpis = llm_input.get("kpis", {})
        flags = llm_input.get("guardrail_flags", [])
        log.info(
            "KPIs: PF=%.2f WR=%.1f%% DD=%.1fR trades=%d | Flags: %s",
            kpis.get("profit_factor", 0),
            kpis.get("win_rate_pct", 0),
            kpis.get("max_drawdown", 0),
            kpis.get("trade_count", 0),
            flags or "none",
        )

        # Step 3: Decide
        decision = decider.decide(llm_input)
        log.info(
            "Decision: %s | Reasons: %s | Changes: %d",
            decision["decision"],
            decision.get("reason_codes", []),
            len(decision.get("changes", [])),
        )
        if decision.get("notes"):
            log.info("Notes: %s", decision["notes"])

        for c in decision.get("changes", []):
            log.info("  Change: %s: %s -> %s", c["path"], c.get("from"), c["to"])

        # Step 4: Apply
        if decision["decision"] in ("ACCEPT", "STOP", "REJECT"):
            log.info("Loop finished: %s", decision["decision"])
            # Log final decision
            log_dir = ROOT / "logs" / "json"
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
            final_log = {
                "timestamp": ts,
                "iteration": iteration,
                "decision": decision["decision"],
                "reason_codes": decision.get("reason_codes", []),
                "kpis": kpis,
                "notes": decision.get("notes", ""),
            }
            (log_dir / f"auto_improve_{ts}.json").write_text(
                json.dumps(final_log, indent=2), encoding="utf-8"
            )
            return 0

        if not apply_decision(decision, args.config, args.dry_run):
            log.error("apply_changes failed, stopping")
            return 1

        if args.dry_run:
            log.info("DRY RUN: would apply changes above, stopping")
            return 0

    log.info("Max iterations reached (%d)", args.max_iter)
    return 0


if __name__ == "__main__":
    sys.exit(main())
