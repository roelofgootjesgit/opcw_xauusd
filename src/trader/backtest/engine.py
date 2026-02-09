"""
Backtest engine: load data, run strategy, record trades.
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.trader.data.schema import Trade, calculate_rr
from src.trader.data.sessions import session_from_timestamp
from src.trader.io.parquet_loader import load_parquet, ensure_data
from src.trader.strategies.sqe_xauusd import run_sqe_conditions, get_sqe_default_config
from src.trader.strategy_modules.ict.structure_context import add_structure_context

logger = logging.getLogger(__name__)


def _deep_merge_sqe(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """Merge override into base (nested dicts for strategy/SQE config)."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge_sqe(base[k], v)
        else:
            base[k] = v


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
        logger.info("No or insufficient data; trying Yahoo Finance (yfinance) fallback...")
        data = ensure_data(symbol=symbol, timeframe=tf, base_path=base_path, period_days=period_days)
    if data.empty or len(data) < 50:
        logger.warning("Still no data. Run: pip install yfinance && oclw_bot fetch")
        return []

    data = data.sort_index()
    strategy_cfg = cfg.get("strategy", {}) or {}
    sqe_cfg = get_sqe_default_config()
    if strategy_cfg:
        _deep_merge_sqe(sqe_cfg, strategy_cfg)
    direction = "LONG"

    long_entries = run_sqe_conditions(data, "LONG", sqe_cfg)
    n_m15 = int(long_entries.sum())
    logger.info("Entry bars (M15, voor H1-gate): %d", n_m15)

    # Stap 1: H1 structure gate optioneel (alleen als structure_use_h1_gate true)
    if strategy_cfg.get("structure_use_h1_gate", False) and "1h" in timeframes and tf != "1h":
        data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
        if not data_1h.empty and len(data_1h) >= 30:
            data_1h = data_1h.sort_index()
            struct_cfg = sqe_cfg.get("structure_context", {"lookback": 30, "pivot_bars": 2})
            data_1h = add_structure_context(data_1h, struct_cfg)
            h1_bullish = data_1h["in_bullish_structure"].reindex(data.index, method="ffill")
            long_entries = long_entries & h1_bullish.fillna(False)
            logger.info("Entry bars (na H1-gate): %d", int(long_entries.sum()))
        else:
            logger.info("H1-gate aan maar geen 1h-data; M15-only")
    else:
        logger.info("H1-gate uit (structure_use_h1_gate=false); alleen M15 structuur")

    # Stap 3: max 1 trade per sessie per richting
    traded_session_direction: set = set()  # (date, session, direction)

    trades: List[Trade] = []

    for i in range(1, len(data) - 1):
        if not long_entries.iloc[i]:
            continue
        entry_ts = data.index[i]
        session_key = (entry_ts.date(), session_from_timestamp(entry_ts), direction)
        if session_key in traded_session_direction:
            continue
        entry_price = float(data.iloc[i]["close"])
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

        t = Trade(
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
        traded_session_direction.add(session_key)
        trades.append(t)
        # Elke trade in de log (voor mensen + data)
        logger.info(
            "Trade #%d | entry %s @ %.2f | exit %s @ %.2f | sl=%.2f tp=%.2f | %s | pnl_usd=%.2f pnl_r=%.2f",
            len(trades),
            t.timestamp_open,
            entry_price,
            t.timestamp_close,
            exit_price,
            sl,
            tp,
            result,
            profit_usd,
            profit_r,
        )

    logger.info("%s %s: %d trades", symbol, tf, len(trades))
    if trades:
        from src.trader.backtest.metrics import compute_metrics
        m = compute_metrics(trades)
        logger.info(
            "Backtest result: net_pnl=%.2f profit_factor=%.2f winrate=%.1f%% max_dd=%.2fR trade_count=%d",
            m.get("net_pnl", 0),
            m.get("profit_factor", 0),
            m.get("win_rate", 0),
            m.get("max_drawdown", 0),
            m.get("trade_count", 0),
        )
    return trades
