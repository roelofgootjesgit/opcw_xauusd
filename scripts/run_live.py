#!/usr/bin/env python3
"""
Live Trading Runner — connects to Oanda and executes the SQE strategy.

Supports:
  - Paper trading (Oanda practice account)
  - Live trading (Oanda live account)
  - Reconnect/recovery on disconnect
  - Regime detection with per-regime configs
  - News filtering
  - Sentiment integration
  - Telegram alerts
  - Spread monitoring

Usage:
  python scripts/run_live.py --config configs/xauusd.yaml
  python scripts/run_live.py --config configs/xauusd.yaml --paper   # paper mode (default)
  python scripts/run_live.py --config configs/xauusd.yaml --live    # live mode
"""
import argparse
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.trader.config import load_config
from src.trader.execution.broker_oanda import OandaBroker, OrderResult
from src.trader.execution.order_manager import OrderManager
from src.trader.execution.account import AccountTracker
from src.trader.data.sessions import session_from_timestamp, ENTRY_SESSIONS
from src.trader.strategies.sqe_xauusd import run_sqe_conditions, get_sqe_default_config
from src.trader.strategy_modules.ict.structure_context import add_structure_context
from src.trader.io.oanda_loader import fetch_oanda_candles, GRANULARITY_MAP

logger = logging.getLogger("live_trader")


class LiveTrader:
    """
    Main live trading loop.

    Flow:
    1. Connect to Oanda
    2. Load historical data for indicator warm-up
    3. Detect current regime
    4. Check news filter
    5. Stream prices and evaluate entries on each new candle
    6. Manage open orders (trailing, BE, partial close)
    7. Send Telegram alerts
    """

    def __init__(self, config: Dict):
        self.config = config
        self.running = False
        self._stop_event = threading.Event()

        # Broker
        broker_cfg = config.get("broker", {})
        self.broker = OandaBroker(
            account_id=broker_cfg.get("account_id") or os.getenv("OANDA_ACCOUNT_ID", ""),
            token=broker_cfg.get("token") or os.getenv("OANDA_TOKEN", ""),
            environment=broker_cfg.get("environment", "practice"),
            instrument=broker_cfg.get("instrument", "XAU_USD"),
        )

        # Account tracker
        risk_cfg = config.get("risk", {})
        self.account = AccountTracker(
            initial_balance=broker_cfg.get("initial_balance", 10000),
            leverage=broker_cfg.get("leverage", 100),
            margin_rate=broker_cfg.get("margin_rate", 0.05),
            risk_pct_per_r=risk_cfg.get("risk_pct_per_r", 0.01),
        )

        # Order manager
        self.order_manager = OrderManager(
            broker=self.broker,
            config=config.get("order_management", {}),
        )

        # Strategy config
        self.strategy_cfg = config.get("strategy", {})
        self.sqe_cfg = get_sqe_default_config()
        if self.strategy_cfg:
            from src.trader.backtest.engine import _deep_merge_sqe
            _deep_merge_sqe(self.sqe_cfg, self.strategy_cfg)

        # Regime detector
        self.regime_detector = None
        try:
            from src.trader.strategy_modules.regime.detector import RegimeDetector
            self.regime_detector = RegimeDetector()
        except ImportError:
            logger.warning("Regime detector not available")

        # News filter
        self.news_cfg = config.get("news_filter", {})
        self.news_events = None
        if self.news_cfg.get("enabled", False):
            try:
                from src.trader.data.news import load_news_calendar
                self.news_events = load_news_calendar()
                logger.info("News filter loaded: %d events", len(self.news_events))
            except Exception as e:
                logger.warning("News filter failed: %s", e)

        # Sentiment engine
        self.sentiment_engine = None
        self.sentiment_cfg = config.get("sentiment", {})
        if self.sentiment_cfg.get("enabled", False):
            try:
                from src.trader.data.sentiment import SentimentEngine
                self.sentiment_engine = SentimentEngine(self.sentiment_cfg)
            except Exception as e:
                logger.warning("Sentiment engine failed: %s", e)

        # Spread monitoring
        self.spread_cfg = config.get("monitoring", {}).get("spread", {})
        self.max_spread = self.spread_cfg.get("max_spread_pips", 40) * 0.01

        # State
        self.current_regime = "UNKNOWN"
        self.last_candle_time = None
        self.candle_buffer_15m: pd.DataFrame = pd.DataFrame()
        self.candle_buffer_1h: pd.DataFrame = pd.DataFrame()

        # Risk limits
        self.max_daily_loss_r = risk_cfg.get("max_daily_loss_r", 2.5)
        self.max_concurrent = risk_cfg.get("max_concurrent_positions", 3)

    def start(self) -> None:
        """Start the live trading loop."""
        logger.info("=" * 60)
        logger.info("Starting Live Trader (%s)", self.broker.environment)
        logger.info("=" * 60)

        # Connect to broker
        if not self.broker.connect():
            logger.error("Failed to connect to Oanda. Exiting.")
            return

        # Sync account
        info = self.broker.get_account_info()
        if info:
            self.account.balance = info.balance
            self.account.equity = info.equity
            self.account.peak_equity = max(self.account.peak_equity, info.equity)
            logger.info("Account: balance=%.2f equity=%.2f margin_avail=%.2f",
                        info.balance, info.equity, info.margin_available)

        # Restore state
        restored = self.order_manager.load_state()
        if restored > 0:
            logger.info("Restored %d managed orders from previous session", restored)

        # Load historical data for warm-up
        self._warm_up()

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Start trading loop
        self.running = True
        self._main_loop()

    def _warm_up(self) -> None:
        """Load recent historical data for indicator calculation."""
        logger.info("Warming up with historical data...")
        try:
            token = self.broker.token
            env = self.broker.environment
            instrument = self.broker.instrument

            self.candle_buffer_15m = fetch_oanda_candles(
                instrument=instrument,
                granularity="M15",
                count=500,
                token=token,
                environment=env,
            )
            self.candle_buffer_1h = fetch_oanda_candles(
                instrument=instrument,
                granularity="H1",
                count=200,
                token=token,
                environment=env,
            )

            logger.info("Warm-up: %d M15 candles, %d H1 candles",
                        len(self.candle_buffer_15m), len(self.candle_buffer_1h))

            # Initial regime detection
            if self.regime_detector and not self.candle_buffer_15m.empty:
                regime_series = self.regime_detector.classify(
                    self.candle_buffer_15m,
                    self.candle_buffer_1h if not self.candle_buffer_1h.empty else None,
                )
                self.current_regime = regime_series.iloc[-1] if not regime_series.empty else "UNKNOWN"
                logger.info("Current regime: %s", self.current_regime)

        except Exception as e:
            logger.error("Warm-up failed: %s", e)

    def _main_loop(self) -> None:
        """Main trading loop — evaluates on each new candle."""
        logger.info("Entering main loop. Checking every 60 seconds for new candles...")

        reconnect_attempts = 0
        max_reconnect = 10
        reconnect_delay = 5  # seconds, will increase exponentially

        while self.running and not self._stop_event.is_set():
            try:
                # Check for new candle
                self._check_new_candle()

                # Update order management with current prices
                self._update_orders()

                # Reset reconnect counter on success
                reconnect_attempts = 0
                reconnect_delay = 5

                # Wait for next check
                self._stop_event.wait(timeout=60)

            except Exception as e:
                logger.error("Main loop error: %s", e)
                reconnect_attempts += 1
                if reconnect_attempts >= max_reconnect:
                    logger.critical("Max reconnect attempts reached. Shutting down.")
                    break

                logger.info("Reconnecting in %ds (attempt %d/%d)...",
                            reconnect_delay, reconnect_attempts, max_reconnect)
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 300)  # Max 5 min

                # Try to reconnect
                try:
                    self.broker.connect()
                except Exception as re:
                    logger.error("Reconnect failed: %s", re)

        logger.info("Main loop exited.")

    def _check_new_candle(self) -> None:
        """Check if a new 15m candle has closed and evaluate signals."""
        try:
            # Fetch latest candles
            new_candles = fetch_oanda_candles(
                instrument=self.broker.instrument,
                granularity="M15",
                count=5,
                token=self.broker.token,
                environment=self.broker.environment,
            )

            if new_candles.empty:
                return

            latest_time = new_candles.index[-1]
            if self.last_candle_time is not None and latest_time <= self.last_candle_time:
                return  # No new candle

            self.last_candle_time = latest_time

            # Append to buffer
            if not self.candle_buffer_15m.empty:
                combined = pd.concat([self.candle_buffer_15m, new_candles])
                combined = combined[~combined.index.duplicated(keep="last")]
                self.candle_buffer_15m = combined.tail(500)  # Keep last 500 candles
            else:
                self.candle_buffer_15m = new_candles

            # Evaluate trading signals
            self._evaluate_signals()

        except Exception as e:
            logger.error("Candle check failed: %s", e)

    def _evaluate_signals(self) -> None:
        """Evaluate SQE strategy signals on the latest data."""
        data = self.candle_buffer_15m
        if len(data) < 50:
            return

        now = datetime.utcnow()
        today = now.strftime("%Y-%m-%d")

        # --- Pre-flight checks ---

        # Daily loss limit
        if not self.account.can_trade(today, self.max_daily_loss_r):
            logger.info("Daily loss limit reached. No more trades today.")
            return

        # Max concurrent positions
        open_trades = self.broker.get_open_trades(self.broker.instrument)
        if len(open_trades) >= self.max_concurrent:
            logger.debug("Max concurrent positions reached (%d)", len(open_trades))
            return

        # Session filter
        current_session = session_from_timestamp(now)
        session_filter = self.config.get("backtest", {}).get("session_filter")
        if session_filter and current_session not in session_filter:
            logger.debug("Outside active session (%s)", current_session)
            return

        # News filter
        if self.news_cfg.get("enabled", False) and self.news_events is not None:
            from src.trader.data.news import is_in_no_trade_zone
            if is_in_no_trade_zone(now, self.news_events, self.news_cfg):
                logger.info("In news no-trade zone. Skipping.")
                return

        # Spread check
        price_info = self.broker.get_current_price()
        if price_info:
            spread = price_info.get("spread", 0)
            if spread > self.max_spread:
                logger.info("Spread too wide: %.2f > %.2f. Skipping.", spread, self.max_spread)
                return

        # --- Regime detection ---
        if self.regime_detector:
            regime_series = self.regime_detector.classify(
                data,
                self.candle_buffer_1h if not self.candle_buffer_1h.empty else None,
            )
            self.current_regime = regime_series.iloc[-1] if not regime_series.empty else "UNKNOWN"

        # --- Get regime-specific config ---
        regime_profiles = self.config.get("regime_profiles", {})
        regime_profile = regime_profiles.get(self.current_regime.lower(), {})
        tp_r = regime_profile.get("tp_r", self.config.get("backtest", {}).get("tp_r", 2.5))
        sl_r = regime_profile.get("sl_r", self.config.get("backtest", {}).get("sl_r", 1.0))

        # --- Generate signals ---
        for direction in ["LONG", "SHORT"]:
            entries = run_sqe_conditions(data, direction, self.sqe_cfg)
            if not entries.iloc[-1]:
                continue

            # H1 gate
            if self.strategy_cfg.get("structure_use_h1_gate", False) and not self.candle_buffer_1h.empty:
                struct_cfg = self.sqe_cfg.get("structure_context", {"lookback": 30, "pivot_bars": 2})
                h1_data = add_structure_context(self.candle_buffer_1h.copy(), struct_cfg)
                col = "in_bullish_structure" if direction == "LONG" else "in_bearish_structure"
                if not h1_data[col].iloc[-1]:
                    logger.debug("H1 gate blocked %s entry", direction)
                    continue

            # Sentiment check
            if self.sentiment_engine:
                sentiment = self.sentiment_engine.fetch_all_data()
                if not self.sentiment_engine.should_allow_trade(sentiment, direction):
                    logger.info("Sentiment blocked %s entry (score=%.2f)", direction, sentiment.score)
                    continue

            # --- Execute trade ---
            entry_price = price_info["ask"] if direction == "LONG" else price_info["bid"]
            atr = (data["high"] - data["low"]).tail(14).mean()
            if pd.isna(atr) or atr <= 0:
                atr = entry_price * 0.005

            if direction == "LONG":
                sl = entry_price - sl_r * atr
                tp = entry_price + tp_r * atr
                oanda_dir = "BUY"
            else:
                sl = entry_price + sl_r * atr
                tp = entry_price - tp_r * atr
                oanda_dir = "SELL"

            # Calculate position size
            sl_distance = abs(entry_price - sl)
            lot_size = self.account.lot_size_for_risk(sl_distance, point_value=1.0)
            units = max(1, round(lot_size))

            # Apply regime position size multiplier
            size_mult = regime_profile.get("position_size_multiplier", 1.0)
            units = max(1, round(units * size_mult))

            logger.info("SIGNAL: %s %s @ %.2f | sl=%.2f tp=%.2f | regime=%s | units=%d",
                        direction, self.broker.instrument, entry_price, sl, tp, self.current_regime, units)

            # Submit order
            result = self.broker.submit_market_order(
                direction=oanda_dir,
                units=units,
                sl=sl,
                tp=tp,
                comment=f"SQE_{direction}_{self.current_regime}",
            )

            if result.success:
                logger.info("ORDER FILLED: %s trade_id=%s @ %.2f",
                            direction, result.trade_id, result.fill_price)

                # Register with order manager
                self.order_manager.register_trade(
                    trade_id=result.trade_id,
                    instrument=self.broker.instrument,
                    direction=direction,
                    entry_price=result.fill_price or entry_price,
                    units=units,
                    sl=sl,
                    tp=tp,
                    atr=atr,
                    regime=self.current_regime,
                    requested_price=entry_price,
                )

                # Record in account tracker
                self.account.open_position(
                    symbol=self.broker.instrument,
                    direction=direction,
                    entry_price=result.fill_price or entry_price,
                    volume=units,
                    sl=sl,
                    tp=tp,
                    timestamp=now,
                )
            else:
                logger.warning("ORDER FAILED: %s — %s", direction, result.message)

    def _update_orders(self) -> None:
        """Update managed orders with current prices."""
        price_info = self.broker.get_current_price()
        if not price_info:
            return

        mid_price = (price_info["bid"] + price_info["ask"]) / 2

        for trade_id in list(self.order_manager.managed_orders.keys()):
            self.order_manager.update_price(trade_id, mid_price)

        # Update account with prices
        self.account.update_prices({self.broker.instrument: mid_price})

    def _handle_shutdown(self, signum, frame) -> None:
        """Graceful shutdown — save state, SL/TP stay on broker."""
        logger.info("Shutdown signal received. Saving state...")
        self.running = False
        self._stop_event.set()
        self.order_manager.save_state()
        logger.info("State saved. SL/TP orders remain active on broker.")
        logger.info("Open positions: %d", len(self.order_manager.managed_orders))

    def stop(self) -> None:
        """Stop the trader gracefully."""
        self._handle_shutdown(None, None)


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Live Trader")
    parser.add_argument("--config", "-c", default="configs/xauusd.yaml", help="Config YAML path")
    parser.add_argument("--paper", action="store_true", default=True, help="Paper trading (default)")
    parser.add_argument("--live", action="store_true", help="Live trading (real money)")
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(ROOT / "logs" / f"live_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.log"),
        ],
    )

    config = load_config(args.config)

    # Override environment for paper/live
    if args.live:
        config.setdefault("broker", {})["environment"] = "live"
        logger.warning("*** LIVE TRADING MODE — REAL MONEY ***")
    else:
        config.setdefault("broker", {})["environment"] = "practice"
        logger.info("Paper trading mode (Oanda practice account)")

    trader = LiveTrader(config)
    trader.start()


if __name__ == "__main__":
    main()
