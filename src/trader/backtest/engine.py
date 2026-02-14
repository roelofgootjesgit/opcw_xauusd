"""
Backtest engine: load data, run strategy, record trades.
Supports LONG + SHORT, session filtering, news filtering, regime detection,
risk management (circuit breaker, max positions, kill switch).
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.trader.data.schema import Trade, calculate_rr
from src.trader.data.sessions import session_from_timestamp, ENTRY_SESSIONS
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


def _apply_h1_gate(
    entries: pd.Series,
    data: pd.DataFrame,
    direction: str,
    base_path: Path,
    symbol: str,
    start: datetime,
    end: datetime,
    sqe_cfg: Dict[str, Any],
) -> pd.Series:
    """Apply H1 structure gate to filter entries against higher-timeframe structure."""
    data_1h = load_parquet(base_path, symbol, "1h", start=start, end=end)
    if data_1h.empty or len(data_1h) < 30:
        logger.info("H1-gate aan maar geen 1h-data; M15-only voor %s", direction)
        return entries
    data_1h = data_1h.sort_index()
    struct_cfg = sqe_cfg.get("structure_context", {"lookback": 30, "pivot_bars": 2})
    data_1h = add_structure_context(data_1h, struct_cfg)
    if direction == "LONG":
        h1_filter = data_1h["in_bullish_structure"].reindex(data.index, method="ffill")
    else:
        h1_filter = data_1h["in_bearish_structure"].reindex(data.index, method="ffill")
    h1_filter = h1_filter.infer_objects(copy=False).fillna(False)
    filtered = entries & h1_filter
    logger.info("Entry bars %s (na H1-gate): %d", direction, int(filtered.sum()))
    return filtered


def _simulate_trade(
    data: pd.DataFrame,
    i: int,
    direction: str,
    tp_r: float,
    sl_r: float,
) -> dict:
    """Simulate a single trade from bar i, return trade details dict."""
    entry_price = float(data.iloc[i]["close"])
    atr = (data["high"] - data["low"]).iloc[max(0, i - 14): i + 1].mean()
    if pd.isna(atr) or atr <= 0:
        atr = entry_price * 0.005

    if direction == "LONG":
        sl = entry_price - sl_r * atr
        tp = entry_price + tp_r * atr
    else:  # SHORT
        sl = entry_price + sl_r * atr
        tp = entry_price - tp_r * atr

    exit_ts = data.index[i]
    exit_price = entry_price
    result = "TIMEOUT"

    for j in range(i + 1, len(data)):
        row = data.iloc[j]
        low, high, close = row["low"], row["high"], row["close"]
        exit_ts = data.index[j]

        if direction == "LONG":
            if low <= sl:
                exit_price = sl
                result = "LOSS"
                break
            if high >= tp:
                exit_price = tp
                result = "WIN"
                break
        else:  # SHORT
            if high >= sl:
                exit_price = sl
                result = "LOSS"
                break
            if low <= tp:
                exit_price = tp
                result = "WIN"
                break

        if j == len(data) - 1:
            exit_price = close
            result = "TIMEOUT"

    profit_usd = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
    profit_r = calculate_rr(entry_price, exit_price, sl, direction)

    return {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "sl": sl,
        "tp": tp,
        "exit_ts": exit_ts,
        "profit_usd": profit_usd,
        "profit_r": profit_r,
        "result": result,
        "atr": atr,
    }


def run_backtest(cfg: Dict[str, Any]) -> List[Trade]:
    symbol = cfg.get("symbol", "XAUUSD")
    timeframes = cfg.get("timeframes", ["15m"])
    tf = timeframes[0]
    base_path = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    period_days = cfg.get("backtest", {}).get("default_period_days", 60)
    tp_r = cfg.get("backtest", {}).get("tp_r", 2.0)
    sl_r = cfg.get("backtest", {}).get("sl_r", 1.0)
    session_filter = cfg.get("backtest", {}).get("session_filter", None)

    # Risk management config
    risk_cfg = cfg.get("risk", {})
    max_daily_loss_r = risk_cfg.get("max_daily_loss_r", 3.0)
    max_concurrent = risk_cfg.get("max_concurrent_positions", 3)
    equity_kill_switch_pct = risk_cfg.get("equity_kill_switch_pct", 10.0)

    # News filter (optional)
    news_cfg = cfg.get("news_filter", {})
    news_enabled = news_cfg.get("enabled", False)
    news_events: Optional[pd.DataFrame] = None
    if news_enabled:
        try:
            from src.trader.data.news import load_news_calendar
            news_events = load_news_calendar(period_days=period_days)
        except Exception as e:
            logger.warning("News filter enabled but failed to load: %s", e)

    # Regime detection (optional)
    regime_cfg = cfg.get("regime_profiles", None)
    regime_series: Optional[pd.Series] = None

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

    # --- Regime detection ---
    try:
        from src.trader.strategy_modules.regime.detector import RegimeDetector
        detector = RegimeDetector()
        data_1h_regime = load_parquet(base_path, symbol, "1h", start=start, end=end)
        if not data_1h_regime.empty:
            data_1h_regime = data_1h_regime.sort_index()
        regime_series = detector.classify(data, data_1h_regime if not data_1h_regime.empty else None)
        data["regime"] = regime_series
        logger.info("Regime detection active. Distribution: %s", regime_series.value_counts().to_dict())
    except ImportError:
        logger.debug("Regime detector not available, skipping")
    except Exception as e:
        logger.warning("Regime detection failed: %s", e)

    # --- Generate entry signals for both directions ---
    long_entries = run_sqe_conditions(data, "LONG", sqe_cfg)
    short_entries = run_sqe_conditions(data, "SHORT", sqe_cfg)
    logger.info("LONG entry bars (M15, pre-filter): %d", int(long_entries.sum()))
    logger.info("SHORT entry bars (M15, pre-filter): %d", int(short_entries.sum()))

    # --- H1 structure gate (optional) ---
    if strategy_cfg.get("structure_use_h1_gate", False) and "1h" in timeframes and tf != "1h":
        long_entries = _apply_h1_gate(long_entries, data, "LONG", base_path, symbol, start, end, sqe_cfg)
        short_entries = _apply_h1_gate(short_entries, data, "SHORT", base_path, symbol, start, end, sqe_cfg)
    else:
        logger.info("H1-gate uit; alleen M15 structuur")

    # --- Session filtering ---
    allowed_sessions = session_filter or list(ENTRY_SESSIONS)
    if session_filter is not None:
        session_mask = data.index.map(lambda ts: session_from_timestamp(ts) in allowed_sessions)
        long_entries = long_entries & session_mask
        short_entries = short_entries & session_mask
        logger.info("Session filter active (%s). LONG: %d, SHORT: %d",
                     allowed_sessions, int(long_entries.sum()), int(short_entries.sum()))

    # --- News filter ---
    news_blocked_count = 0
    if news_enabled and news_events is not None and not news_events.empty:
        try:
            from src.trader.data.news import is_in_no_trade_zone
            news_mask = data.index.map(lambda ts: not is_in_no_trade_zone(ts, news_events, news_cfg))
            long_entries = long_entries & news_mask
            short_entries = short_entries & news_mask
            news_blocked_count = int((~news_mask).sum())
            logger.info("News filter blocked %d bars from trading", news_blocked_count)
        except Exception as e:
            logger.warning("News filter application failed: %s", e)

    # --- Combine all entries (LONG + SHORT) into ordered list ---
    entry_signals = []
    for i in range(1, len(data) - 1):
        if long_entries.iloc[i]:
            entry_signals.append((i, "LONG"))
        if short_entries.iloc[i]:
            entry_signals.append((i, "SHORT"))

    # --- Risk management state ---
    traded_session_direction: set = set()
    daily_pnl_r: Dict[Any, float] = {}  # date -> cumulative R for the day
    cumulative_r = 0.0
    peak_r = 0.0
    kill_switch_triggered = False
    trades: List[Trade] = []

    for i, direction in entry_signals:
        entry_ts = data.index[i]
        trade_date = entry_ts.date()

        # --- Kill switch check ---
        if kill_switch_triggered:
            break

        # --- Max daily loss circuit breaker ---
        day_r = daily_pnl_r.get(trade_date, 0.0)
        if day_r <= -max_daily_loss_r:
            logger.debug("Daily loss limit hit (%.2fR) on %s, skipping", day_r, trade_date)
            continue

        # --- Equity kill switch (cumulative drawdown) ---
        dd_from_peak = peak_r - cumulative_r
        if dd_from_peak >= equity_kill_switch_pct:
            logger.warning("Equity kill switch triggered: drawdown %.2fR from peak", dd_from_peak)
            kill_switch_triggered = True
            break

        # --- Session + direction dedup (max 1 trade per session per direction) ---
        session_key = (trade_date, session_from_timestamp(entry_ts), direction)
        if session_key in traded_session_direction:
            continue

        # --- Get regime-specific TP/SL if regime_profiles configured ---
        trade_tp_r = tp_r
        trade_sl_r = sl_r
        if regime_cfg and regime_series is not None and i < len(regime_series):
            current_regime = regime_series.iloc[i]
            regime_profile = regime_cfg.get(current_regime.lower(), {}) if isinstance(current_regime, str) else {}
            if regime_profile:
                trade_tp_r = regime_profile.get("tp_r", tp_r)
                trade_sl_r = regime_profile.get("sl_r", sl_r)

        # --- Simulate the trade ---
        result = _simulate_trade(data, i, direction, trade_tp_r, trade_sl_r)

        t = Trade(
            timestamp_open=entry_ts,
            timestamp_close=result["exit_ts"],
            symbol=symbol,
            direction=direction,
            entry_price=result["entry_price"],
            exit_price=result["exit_price"],
            sl=result["sl"],
            tp=result["tp"],
            profit_usd=result["profit_usd"],
            profit_r=result["profit_r"],
            result=result["result"],
        )
        traded_session_direction.add(session_key)
        trades.append(t)

        # Update risk tracking
        cumulative_r += result["profit_r"]
        if cumulative_r > peak_r:
            peak_r = cumulative_r
        daily_pnl_r[trade_date] = daily_pnl_r.get(trade_date, 0.0) + result["profit_r"]

        logger.info(
            "Trade #%d %s | entry %s @ %.2f | exit %s @ %.2f | sl=%.2f tp=%.2f | %s | pnl_usd=%.2f pnl_r=%.2f",
            len(trades),
            direction,
            t.timestamp_open,
            result["entry_price"],
            t.timestamp_close,
            result["exit_price"],
            result["sl"],
            result["tp"],
            result["result"],
            result["profit_usd"],
            result["profit_r"],
        )

    logger.info("%s %s: %d trades (LONG: %d, SHORT: %d)", symbol, tf, len(trades),
                sum(1 for t in trades if t.direction == "LONG"),
                sum(1 for t in trades if t.direction == "SHORT"))
    if kill_switch_triggered:
        logger.warning("Kill switch was triggered during backtest")
    if news_blocked_count > 0:
        logger.info("News filter blocked %d potential entry bars", news_blocked_count)

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
