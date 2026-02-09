"""
Backtest engine: load data, run strategy, record trades.
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.trader.data.schema import Trade, calculate_rr
from src.trader.io.parquet_loader import load_parquet
from src.trader.strategies.sqe_xauusd import run_sqe_conditions, get_sqe_default_config


def run_backtest(cfg: Dict[str, Any]) -> List[Trade]:
    symbol = cfg.get("symbol", "XAUUSD")
    timeframes = cfg.get("timeframes", ["15m"])
    tf = timeframes[0]
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    period_days = cfg.get("backtest", {}).get("default_period_days", 60)
    tp_r = cfg.get("backtest", {}).get("tp_r", 2.0)
    sl_r = cfg.get("backtest", {}).get("sl_r", 1.0)

    end = datetime.now()
    start = end - timedelta(days=period_days)
    data = load_parquet(base_path, symbol, tf, start=start, end=end)
    if data.empty or len(data) < 50:
        print("[Backtest] No or insufficient data; run 'fetch' first or add Parquet under data/market_cache/XAUUSD/")
        return []

    data = data.sort_index()
    strategy_cfg = cfg.get("strategy", {}) or {}
    sqe_cfg = get_sqe_default_config()
    direction = "LONG"

    long_entries = run_sqe_conditions(data, "LONG", sqe_cfg)
    trades: List[Trade] = []

    for i in range(1, len(data) - 1):
        if not long_entries.iloc[i]:
            continue
        entry_price = float(data.iloc[i]["close"])
        entry_ts = data.index[i]
        atr = (data["high"] - data["low"]).iloc[max(0, i - 14) : i + 1].mean()
        if pd.isna(atr) or atr <= 0:
            atr = entry_price * 0.005
        sl = entry_price - sl_r * atr
        tp = entry_price + tp_r * atr
        exit_ts = data.index[i]
        exit_price = entry_price
        result = "TIMEOUT"
        for j in range(i + 1, len(data)):
            row = data.iloc[j]
            low, high, close = row["low"], row["high"], row["close"]
            exit_ts = data.index[j]
            if low <= sl:
                exit_price = sl
                result = "LOSS"
                break
            if high >= tp:
                exit_price = tp
                result = "WIN"
                break
            if j == len(data) - 1:
                exit_price = close
                result = "TIMEOUT"

        risk = abs(entry_price - sl)
        profit_usd = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
        profit_r = calculate_rr(entry_price, exit_price, sl, direction)

        trades.append(
            Trade(
                timestamp_open=entry_ts,
                timestamp_close=exit_ts,
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                exit_price=exit_price,
                sl=sl,
                tp=tp,
                profit_usd=profit_usd,
                profit_r=profit_r,
                result=result,
            )
        )

    print(f"[Backtest] {symbol} {tf}: {len(trades)} trades")
    return trades
