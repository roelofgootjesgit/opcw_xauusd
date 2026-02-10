#!/usr/bin/env python3
"""
Telegram gateway: RUN_BACKTEST → run backtest → send report back.
Single module; no Improver, no ML. Proves the loop is reliable.
Usage: TELEGRAM_BOT_TOKEN=... python scripts/telegram_listener.py
Requires: pip install ".[telegram]"
"""
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
except ImportError:
    print("Install telegram: pip install '.[telegram]'", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
BACKTEST_TIMEOUT = 300  # 5 min max
TELEGRAM_MAX_MESSAGE = 4096  # Telegram limit


def _run_ts() -> str:
    return time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())


def _acquire_lock() -> bool:
    sys.path.insert(0, str(ROOT))
    from scripts.run_lock import acquire
    return acquire("backtest")


def _release_lock() -> None:
    sys.path.insert(0, str(ROOT))
    from scripts.run_lock import release
    release()


def _run_backtest_to_artifacts(out_dir: Path, config: str = "configs/xauusd.yaml") -> tuple[int, str]:
    """Run backtest script; return (exit_code, out_dir as str)."""
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_backtest_to_artifacts.py"),
        "--config", config,
        "--out", str(out_dir),
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=BACKTEST_TIMEOUT,
    )
    return proc.returncode, str(out_dir)


async def cmd_run_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /run_backtest or RUN_BACKTEST: run backtest, send report."""
    if not _acquire_lock():
        await update.message.reply_text("⏳ Backtest already running. Try again later.")
        return

    run_ts = _run_ts()
    out_dir = ARTIFACTS / f"run_{run_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    await update.message.reply_text(f"🔄 Backtest started (run_{run_ts}). Wait…")

    try:
        config_path = (context.args[0] if context.args else "configs/xauusd.yaml").strip()
        exit_code, _ = await asyncio.to_thread(
            _run_backtest_to_artifacts,
            out_dir,
            config_path,
        )
    except subprocess.TimeoutExpired:
        _release_lock()
        await update.message.reply_text(f"❌ Backtest timed out after {BACKTEST_TIMEOUT}s.")
        return
    except Exception as e:
        _release_lock()
        await update.message.reply_text(f"❌ Error: {e}")
        return

    _release_lock()

    report_md = out_dir / "report.md"
    metrics_json = out_dir / "metrics.json"

    if exit_code != 0:
        err_msg = "Backtest failed."
        if metrics_json.exists():
            import json
            data = json.loads(metrics_json.read_text(encoding="utf-8"))
            if "error" in data:
                err_msg = data["error"][:500]
        await update.message.reply_text(f"❌ {err_msg}")
        return

    # Send report (MD + core metrics)
    if report_md.exists():
        text = report_md.read_text(encoding="utf-8")
        if len(text) > TELEGRAM_MAX_MESSAGE:
            text = text[: TELEGRAM_MAX_MESSAGE - 50] + "\n\n… (truncated)"
        await update.message.reply_text(f"```\n{text}\n```", parse_mode=None)
    else:
        summary = "Run finished; report.md missing."
        if metrics_json.exists():
            import json
            data = json.loads(metrics_json.read_text(encoding="utf-8"))
            k = data.get("kpis", {})
            summary = (
                f"Run {run_ts}\n"
                f"net_pnl={k.get('net_pnl', 0):.2f} PF={k.get('profit_factor', 0):.2f} "
                f"winrate={k.get('win_rate_pct', 0):.1f}% trades={k.get('trade_count', 0)}"
            )
        await update.message.reply_text(summary)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commands:\n"
        "/run_backtest [config] — Run backtest, get report (default config: configs/xauusd.yaml)\n"
        "/help — This message"
    )


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN or BOT_TOKEN", file=sys.stderr)
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("run_backtest", cmd_run_backtest))
    app.add_handler(CommandHandler("help", cmd_help))

    async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message and update.message.text and update.message.text.strip().upper() == "RUN_BACKTEST":
            await cmd_run_backtest(update, context)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("Telegram listener running. Commands: /run_backtest, /help, RUN_BACKTEST")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
