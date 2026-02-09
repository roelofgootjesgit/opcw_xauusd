"""
CLI entrypoint: backtest, fetch, etc.
"""
import argparse
import sys
from pathlib import Path

from src.trader.config import load_config
from src.trader.logging_config import setup_logging


def cmd_backtest(args: argparse.Namespace) -> int:
    from src.trader.backtest.engine import run_backtest
    cfg = load_config(args.config)
    setup_logging(cfg)
    run_backtest(cfg)
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    from src.trader.io.parquet_loader import ensure_data
    cfg = load_config(args.config)
    setup_logging(cfg)
    base = cfg.get("data", {}).get("base_path", "data/market_cache")
    ensure_data(
        symbol=args.symbol or cfg.get("symbol", "XAUUSD"),
        timeframe=args.timeframe or "15m",
        base_path=Path(base),
        period_days=args.days or 60,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="openclaw", description="OpenClaw trader CLI")
    parser.add_argument("--config", "-c", default=None, help="Path to YAML config")
    sub = parser.add_subparsers(dest="command", required=True)

    backtest_p = sub.add_parser("backtest", help="Run backtest")
    backtest_p.set_defaults(func=cmd_backtest)

    fetch_p = sub.add_parser("fetch", help="Fetch/cache market data")
    fetch_p.add_argument("--symbol", "-s", default=None)
    fetch_p.add_argument("--timeframe", "-t", default=None)
    fetch_p.add_argument("--days", "-d", type=int, default=None)
    fetch_p.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
