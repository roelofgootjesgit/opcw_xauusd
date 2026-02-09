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
    if getattr(args, "days", None) is not None:
        cfg.setdefault("backtest", {})["default_period_days"] = args.days
    setup_logging(cfg)
    run_backtest(cfg)
    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    from src.trader.ml import ContinuousLearningAgent
    cfg = load_config(args.config)
    setup_logging(cfg)
    agent = ContinuousLearningAgent(
        base_config=cfg,
        candidates_per_cycle=args.candidates,
    )
    for i in range(args.cycles):
        result = agent.run_learning_cycle()
        if "error" in result:
            print(f"[Optimize] Cycle {i+1}: {result['error']}")
        else:
            print(f"[Optimize] Cycle {i+1}: best_reward={result.get('best_reward')} n={result.get('n_evaluated')}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    from src.trader.io.parquet_loader import ensure_data
    cfg = load_config(args.config)
    setup_logging(cfg)
    base = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    symbol = args.symbol or cfg.get("symbol", "XAUUSD")
    period_days = args.days or cfg.get("backtest", {}).get("default_period_days", 60)
    if args.timeframe:
        timeframes = [args.timeframe]
    else:
        timeframes = cfg.get("timeframes", ["15m", "1h"])
    for tf in timeframes:
        ensure_data(symbol=symbol, timeframe=tf, base_path=base, period_days=period_days)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="oclw_bot", description="oclw_bot trader CLI")
    parser.add_argument("--config", "-c", default=None, help="Path to YAML config")
    sub = parser.add_subparsers(dest="command", required=True)

    backtest_p = sub.add_parser("backtest", help="Run backtest")
    backtest_p.add_argument("--days", "-d", type=int, default=None, help="Override period (days) for this run, e.g. 30 for 1 month")
    backtest_p.set_defaults(func=cmd_backtest)

    fetch_p = sub.add_parser("fetch", help="Fetch/cache market data")
    fetch_p.add_argument("--symbol", "-s", default=None)
    fetch_p.add_argument("--timeframe", "-t", default=None)
    fetch_p.add_argument("--days", "-d", type=int, default=None)
    fetch_p.set_defaults(func=cmd_fetch)

    optimize_p = sub.add_parser("optimize", help="Run ML strategy optimization (learning cycle)")
    optimize_p.add_argument("--cycles", "-n", type=int, default=1, help="Number of learning cycles")
    optimize_p.add_argument("--candidates", type=int, default=5, help="Candidates per cycle")
    optimize_p.set_defaults(func=cmd_optimize)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
