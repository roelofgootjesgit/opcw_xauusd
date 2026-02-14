#!/usr/bin/env python3
"""
Telegram gateway: live trading dashboard + backtest runner.

Commands:
  /run_backtest [config] — Run backtest, get report
  /status — Account status + open positions
  /equity — Equity/balance summary
  /regime — Current market regime
  /stop — Pause live trading
  /resume — Resume live trading
  /help — Show all commands

Also sends proactive alerts:
  - Trade entry/exit
  - Daily P&L summary
  - Error/disconnect alerts
  - Regime changes
  - Kill switch triggers

Usage: TELEGRAM_BOT_TOKEN=... python scripts/telegram_listener.py
Requires: pip install ".[telegram]"
"""
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
except ImportError:
    print("Install telegram: pip install '.[telegram]'", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
BACKTEST_TIMEOUT = 300  # 5 min max
TELEGRAM_MAX_MESSAGE = 4096  # Telegram limit

# Global state for live trading integration
_live_trader = None
_trading_paused = False


def _run_ts() -> str:
    return time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())


def _acquire_lock() -> bool:
    from scripts.run_lock import acquire
    return acquire("backtest")


def _release_lock() -> None:
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


# ────────────────────────────────────────────────────
# Backtest command
# ────────────────────────────────────────────────────
async def cmd_run_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /run_backtest: run backtest, send report."""
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
            _run_backtest_to_artifacts, out_dir, config_path,
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
            data = json.loads(metrics_json.read_text(encoding="utf-8"))
            if "error" in data:
                err_msg = data["error"][:500]
        await update.message.reply_text(f"❌ {err_msg}")
        return

    if report_md.exists():
        text = report_md.read_text(encoding="utf-8")
        if len(text) > TELEGRAM_MAX_MESSAGE:
            text = text[: TELEGRAM_MAX_MESSAGE - 50] + "\n\n… (truncated)"
        await update.message.reply_text(f"```\n{text}\n```", parse_mode=None)
    else:
        summary = "Run finished; report.md missing."
        if metrics_json.exists():
            data = json.loads(metrics_json.read_text(encoding="utf-8"))
            k = data.get("kpis", {})
            summary = (
                f"Run {run_ts}\n"
                f"net_pnl={k.get('net_pnl', 0):.2f} PF={k.get('profit_factor', 0):.2f} "
                f"winrate={k.get('win_rate_pct', 0):.1f}% trades={k.get('trade_count', 0)}"
            )
        await update.message.reply_text(summary)


# ────────────────────────────────────────────────────
# Live trading commands
# ────────────────────────────────────────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current trading status: account, positions, regime."""
    lines = ["📊 *Trading Status*\n"]

    if _live_trader:
        # Account info
        info = _live_trader.broker.get_account_info()
        if info:
            pnl = info.equity - _live_trader.account.initial_balance
            lines.append(f"💰 Balance: ${info.balance:,.2f}")
            lines.append(f"📈 Equity: ${info.equity:,.2f}")
            lines.append(f"{'🟢' if pnl >= 0 else '🔴'} P&L: ${pnl:+,.2f}")
            lines.append(f"📉 Margin used: ${info.margin_used:,.2f}")
            lines.append(f"📊 Open trades: {info.open_trade_count}")
            lines.append("")

        # Regime
        lines.append(f"🏷 Regime: {_live_trader.current_regime}")
        lines.append(f"⏸ Paused: {'Yes' if _trading_paused else 'No'}")
        lines.append(f"🌐 Environment: {_live_trader.broker.environment}")

        # Open positions
        positions = _live_trader.broker.get_open_trades()
        if positions:
            lines.append("\n📋 *Open Positions:*")
            for p in positions:
                emoji = "🟢" if p.unrealized_pnl >= 0 else "🔴"
                lines.append(
                    f"  {emoji} {p.direction} {p.units}u @ {p.entry_price:.2f} "
                    f"| P&L: ${p.unrealized_pnl:+,.2f} "
                    f"| SL: {p.sl or '-'} TP: {p.tp or '-'}"
                )

        # Order manager summary
        om_summary = _live_trader.order_manager.get_summary()
        if om_summary["active_orders"] > 0:
            lines.append(f"\n🔧 Managed orders: {om_summary['active_orders']}")
            for tid, info in om_summary["orders"].items():
                flags = []
                if info["be_set"]:
                    flags.append("BE")
                if info["partial"]:
                    flags.append("PARTIAL")
                if info["trailing"]:
                    flags.append("TRAIL")
                flag_str = " [" + ",".join(flags) + "]" if flags else ""
                lines.append(f"  {tid}: {info['direction']} sl={info['sl']:.2f}{flag_str}")
    else:
        lines.append("⚠️ Live trader not running.")
        lines.append("Start with: python scripts/run_live.py")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_equity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show equity and balance details."""
    if not _live_trader:
        await update.message.reply_text("⚠️ Live trader not running.")
        return

    info = _live_trader.broker.get_account_info()
    acct = _live_trader.account
    if not info:
        await update.message.reply_text("❌ Could not fetch account info.")
        return

    lines = [
        "💰 *Account Summary*\n",
        f"Balance: ${info.balance:,.2f}",
        f"Equity (NAV): ${info.equity:,.2f}",
        f"Unrealized P&L: ${info.unrealized_pnl:+,.2f}",
        f"Margin used: ${info.margin_used:,.2f}",
        f"Free margin: ${info.margin_available:,.2f}",
        "",
        f"Peak equity: ${acct.peak_equity:,.2f}",
        f"Drawdown: {acct.drawdown_pct:.1f}% / {acct.drawdown_r:.1f}R",
        f"Net P&L: ${info.equity - acct.initial_balance:+,.2f}",
        f"Total trades: {len(acct.closed_trades)}",
    ]

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_regime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current market regime."""
    if not _live_trader:
        await update.message.reply_text("⚠️ Live trader not running.")
        return

    regime = _live_trader.current_regime
    emoji = {"TRENDING": "📈", "RANGING": "↔️", "VOLATILE": "⚡"}.get(regime, "❓")

    lines = [
        f"{emoji} *Current Regime: {regime}*\n",
    ]

    # Regime-specific settings
    profiles = _live_trader.config.get("regime_profiles", {})
    profile = profiles.get(regime.lower(), {})
    if profile:
        lines.append("Active settings:")
        lines.append(f"  TP/SL: {profile.get('tp_r', '?')}R / {profile.get('sl_r', '?')}R")
        lines.append(f"  Size mult: {profile.get('position_size_multiplier', 1.0)}x")
        lines.append(f"  Max trades/session: {profile.get('max_trades_per_session', '?')}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause live trading (keeps existing positions)."""
    global _trading_paused
    _trading_paused = True
    if _live_trader:
        _live_trader.running = False
    await update.message.reply_text(
        "⏸ Trading paused.\n"
        "Existing positions and SL/TP orders remain active.\n"
        "Use /resume to continue."
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume live trading."""
    global _trading_paused
    _trading_paused = False
    if _live_trader:
        _live_trader.running = True
    await update.message.reply_text("▶️ Trading resumed.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all available commands."""
    await update.message.reply_text(
        "🤖 *OpenClaw XAUUSD Bot*\n\n"
        "*Trading:*\n"
        "/status — Account + open positions\n"
        "/equity — Balance & equity details\n"
        "/regime — Current market regime\n"
        "/stop — Pause trading\n"
        "/resume — Resume trading\n\n"
        "*Backtest:*\n"
        "/run\\_backtest [config] — Run backtest\n\n"
        "/help — This message",
        parse_mode="Markdown",
    )


# ────────────────────────────────────────────────────
# Alert functions (called from LiveTrader)
# ────────────────────────────────────────────────────
async def send_trade_alert(app: Application, chat_id: int, trade_data: dict) -> None:
    """Send trade entry/exit alert."""
    direction = trade_data.get("direction", "?")
    action = trade_data.get("action", "ENTRY")
    price = trade_data.get("price", 0)
    sl = trade_data.get("sl", 0)
    tp = trade_data.get("tp", 0)
    pnl = trade_data.get("pnl", 0)
    regime = trade_data.get("regime", "?")

    if action == "ENTRY":
        emoji = "🟢" if direction == "LONG" else "🔴"
        msg = (
            f"{emoji} *{action}: {direction}*\n"
            f"Price: {price:.2f}\n"
            f"SL: {sl:.2f} | TP: {tp:.2f}\n"
            f"Regime: {regime}"
        )
    else:
        emoji = "✅" if pnl >= 0 else "❌"
        msg = (
            f"{emoji} *{action}: {direction}*\n"
            f"Price: {price:.2f}\n"
            f"P&L: ${pnl:+,.2f}\n"
            f"Regime: {regime}"
        )

    try:
        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Telegram alert error: {e}", file=sys.stderr)


async def send_daily_summary(app: Application, chat_id: int, summary: dict) -> None:
    """Send daily P&L summary."""
    msg = (
        f"📊 *Daily Summary — {summary.get('date', 'today')}*\n\n"
        f"Trades: {summary.get('trade_count', 0)}\n"
        f"P&L: ${summary.get('pnl', 0):+,.2f}\n"
        f"Win rate: {summary.get('winrate', 0):.0f}%\n"
        f"Regime: {summary.get('regime', '?')}\n"
        f"Balance: ${summary.get('balance', 0):,.2f}"
    )
    try:
        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
    except Exception as e:
        print(f"Telegram summary error: {e}", file=sys.stderr)


async def send_error_alert(app: Application, chat_id: int, error_msg: str) -> None:
    """Send error/warning alert."""
    try:
        await app.bot.send_message(
            chat_id=chat_id,
            text=f"🚨 *ALERT*\n\n{error_msg}",
            parse_mode="Markdown",
        )
    except Exception as e:
        print(f"Telegram error alert failed: {e}", file=sys.stderr)


# ────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────
def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN or BOT_TOKEN", file=sys.stderr)
        sys.exit(1)

    app = Application.builder().token(token).build()

    # Register all commands
    app.add_handler(CommandHandler("run_backtest", cmd_run_backtest))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("equity", cmd_equity))
    app.add_handler(CommandHandler("regime", cmd_regime))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("help", cmd_help))

    # Text message handler (legacy support)
    async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message and update.message.text:
            text = update.message.text.strip().upper()
            if text == "RUN_BACKTEST":
                await cmd_run_backtest(update, context)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("Telegram listener running. Commands: /status, /equity, /regime, /stop, /resume, /run_backtest, /help")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
