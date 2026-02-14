"""
Order Manager — manages the lifecycle of live orders.

Features:
  - Trailing stop management
  - Break-even after X R profit
  - Partial close (e.g. 50% at 1R, rest trailing)
  - Order timeout (cancel if not filled)
  - Slippage tracking
  - State persistence for recovery
"""
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
STATE_FILE = ROOT / "data" / "state.json"


@dataclass
class ManagedOrder:
    """An actively managed order/trade."""
    trade_id: str
    instrument: str
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    units: float
    original_sl: float
    original_tp: float
    current_sl: float
    current_tp: float
    open_time: datetime
    atr_at_entry: float = 0.0
    regime_at_entry: str = ""
    # State
    partial_closed: bool = False
    break_even_set: bool = False
    trailing_active: bool = False
    peak_price: float = 0.0  # Highest (LONG) or lowest (SHORT) price since entry
    # Metadata
    slippage: float = 0.0
    requested_price: float = 0.0


# Default order management config
DEFAULT_ORDER_CONFIG = {
    "trailing_stop": {
        "enabled": True,
        "activation_r": 1.5,  # Start trailing after 1.5R profit
        "trail_distance_r": 1.0,  # Trail SL at 1.0R behind price
    },
    "break_even": {
        "enabled": True,
        "trigger_r": 1.0,  # Move SL to BE after 1R profit
        "offset_pips": 2,  # Move SL slightly above/below entry (cover spread)
    },
    "partial_close": {
        "enabled": True,
        "trigger_r": 1.0,  # Take partial at 1R
        "close_pct": 50,  # Close 50% of position
    },
    "timeout": {
        "enabled": False,
        "max_minutes": 30,  # Cancel if not filled within 30 min (for limit orders)
    },
}


class OrderManager:
    """
    Manages live orders with trailing stops, break-even, partial close, etc.
    Works with OandaBroker for order execution.
    """

    def __init__(
        self,
        broker=None,
        config: Optional[Dict] = None,
    ):
        self.broker = broker
        self.config = {**DEFAULT_ORDER_CONFIG, **(config or {})}
        self.managed_orders: Dict[str, ManagedOrder] = {}
        self._callbacks: List[Callable] = []

    def add_callback(self, callback: Callable[[str, ManagedOrder, Dict], None]) -> None:
        """Add callback for order events (fill, close, modify, etc.)."""
        self._callbacks.append(callback)

    def _notify(self, event: str, order: ManagedOrder, details: Dict = None) -> None:
        """Notify all callbacks of an order event."""
        for cb in self._callbacks:
            try:
                cb(event, order, details or {})
            except Exception as e:
                logger.warning("Callback error: %s", e)

    def register_trade(
        self,
        trade_id: str,
        instrument: str,
        direction: str,
        entry_price: float,
        units: float,
        sl: float,
        tp: float,
        atr: float = 0.0,
        regime: str = "",
        requested_price: float = 0.0,
    ) -> ManagedOrder:
        """Register a new trade for management."""
        slippage = abs(entry_price - requested_price) if requested_price > 0 else 0.0

        order = ManagedOrder(
            trade_id=trade_id,
            instrument=instrument,
            direction=direction,
            entry_price=entry_price,
            units=units,
            original_sl=sl,
            original_tp=tp,
            current_sl=sl,
            current_tp=tp,
            open_time=datetime.utcnow(),
            atr_at_entry=atr,
            regime_at_entry=regime,
            peak_price=entry_price,
            slippage=slippage,
            requested_price=requested_price,
        )
        self.managed_orders[trade_id] = order
        self._notify("REGISTERED", order)
        self.save_state()
        logger.info("Registered trade %s: %s %s @ %.2f sl=%.2f tp=%.2f",
                     trade_id, direction, instrument, entry_price, sl, tp)
        return order

    def update_price(self, trade_id: str, current_price: float) -> None:
        """
        Update current price for a managed trade.
        Handles trailing stop, break-even, and partial close logic.
        """
        order = self.managed_orders.get(trade_id)
        if not order:
            return

        cfg = self.config
        risk = abs(order.entry_price - order.original_sl)
        if risk <= 0:
            return

        # Update peak price
        if order.direction == "LONG":
            current_r = (current_price - order.entry_price) / risk
            if current_price > order.peak_price:
                order.peak_price = current_price
        else:
            current_r = (order.entry_price - current_price) / risk
            if current_price < order.peak_price or order.peak_price == order.entry_price:
                order.peak_price = current_price

        # --- Break-even ---
        be_cfg = cfg.get("break_even", {})
        if be_cfg.get("enabled", True) and not order.break_even_set and current_r >= be_cfg.get("trigger_r", 1.0):
            offset = be_cfg.get("offset_pips", 2) * 0.01  # Convert pips to price
            if order.direction == "LONG":
                new_sl = order.entry_price + offset
            else:
                new_sl = order.entry_price - offset

            if self._modify_sl(trade_id, new_sl):
                order.current_sl = new_sl
                order.break_even_set = True
                self._notify("BREAK_EVEN", order, {"new_sl": new_sl, "profit_r": current_r})
                logger.info("Trade %s: break-even set at %.2f (%.1fR profit)", trade_id, new_sl, current_r)

        # --- Partial close ---
        pc_cfg = cfg.get("partial_close", {})
        if (pc_cfg.get("enabled", True) and not order.partial_closed
                and current_r >= pc_cfg.get("trigger_r", 1.0)):
            close_pct = pc_cfg.get("close_pct", 50)
            units_to_close = round(order.units * close_pct / 100)
            if units_to_close > 0 and self._partial_close(trade_id, units_to_close):
                order.partial_closed = True
                order.units -= units_to_close
                self._notify("PARTIAL_CLOSE", order, {
                    "closed_units": units_to_close,
                    "remaining_units": order.units,
                    "profit_r": current_r,
                })
                logger.info("Trade %s: partial close %d units at %.1fR", trade_id, units_to_close, current_r)

        # --- Trailing stop ---
        ts_cfg = cfg.get("trailing_stop", {})
        if ts_cfg.get("enabled", True) and current_r >= ts_cfg.get("activation_r", 1.5):
            trail_distance = ts_cfg.get("trail_distance_r", 1.0) * risk
            if order.direction == "LONG":
                new_sl = order.peak_price - trail_distance
                if new_sl > order.current_sl:
                    if self._modify_sl(trade_id, new_sl):
                        order.current_sl = new_sl
                        order.trailing_active = True
                        self._notify("TRAILING_STOP", order, {"new_sl": new_sl, "profit_r": current_r})
                        logger.debug("Trade %s: trailing stop updated to %.2f", trade_id, new_sl)
            else:
                new_sl = order.peak_price + trail_distance
                if new_sl < order.current_sl:
                    if self._modify_sl(trade_id, new_sl):
                        order.current_sl = new_sl
                        order.trailing_active = True
                        self._notify("TRAILING_STOP", order, {"new_sl": new_sl, "profit_r": current_r})
                        logger.debug("Trade %s: trailing stop updated to %.2f", trade_id, new_sl)

    def _modify_sl(self, trade_id: str, new_sl: float) -> bool:
        """Modify SL via broker."""
        if self.broker:
            return self.broker.modify_trade(trade_id, sl=new_sl)
        return True  # In backtest mode, always succeeds

    def _partial_close(self, trade_id: str, units: float) -> bool:
        """Partial close via broker."""
        if self.broker:
            return self.broker.close_trade(trade_id, units=units)
        return True

    def unregister_trade(self, trade_id: str, reason: str = "closed") -> Optional[ManagedOrder]:
        """Remove a trade from management."""
        order = self.managed_orders.pop(trade_id, None)
        if order:
            self._notify("UNREGISTERED", order, {"reason": reason})
            self.save_state()
            logger.info("Unregistered trade %s: %s", trade_id, reason)
        return order

    def save_state(self) -> None:
        """Save current state to disk for recovery."""
        state = {}
        for tid, order in self.managed_orders.items():
            state[tid] = {
                "trade_id": order.trade_id,
                "instrument": order.instrument,
                "direction": order.direction,
                "entry_price": order.entry_price,
                "units": order.units,
                "original_sl": order.original_sl,
                "original_tp": order.original_tp,
                "current_sl": order.current_sl,
                "current_tp": order.current_tp,
                "open_time": order.open_time.isoformat(),
                "atr_at_entry": order.atr_at_entry,
                "regime_at_entry": order.regime_at_entry,
                "partial_closed": order.partial_closed,
                "break_even_set": order.break_even_set,
                "trailing_active": order.trailing_active,
                "peak_price": order.peak_price,
                "slippage": order.slippage,
            }

        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")

    def load_state(self) -> int:
        """Load state from disk. Returns number of restored orders."""
        if not STATE_FILE.exists():
            return 0

        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            for tid, data in state.items():
                order = ManagedOrder(
                    trade_id=data["trade_id"],
                    instrument=data["instrument"],
                    direction=data["direction"],
                    entry_price=data["entry_price"],
                    units=data["units"],
                    original_sl=data["original_sl"],
                    original_tp=data["original_tp"],
                    current_sl=data["current_sl"],
                    current_tp=data["current_tp"],
                    open_time=datetime.fromisoformat(data["open_time"]),
                    atr_at_entry=data.get("atr_at_entry", 0),
                    regime_at_entry=data.get("regime_at_entry", ""),
                    partial_closed=data.get("partial_closed", False),
                    break_even_set=data.get("break_even_set", False),
                    trailing_active=data.get("trailing_active", False),
                    peak_price=data.get("peak_price", data["entry_price"]),
                    slippage=data.get("slippage", 0),
                )
                self.managed_orders[tid] = order

            logger.info("Restored %d managed orders from state", len(self.managed_orders))
            return len(self.managed_orders)

        except Exception as e:
            logger.error("Failed to load state: %s", e)
            return 0

    def get_summary(self) -> dict:
        """Get summary of all managed orders."""
        return {
            "active_orders": len(self.managed_orders),
            "orders": {
                tid: {
                    "direction": o.direction,
                    "entry": o.entry_price,
                    "sl": o.current_sl,
                    "tp": o.current_tp,
                    "be_set": o.break_even_set,
                    "partial": o.partial_closed,
                    "trailing": o.trailing_active,
                    "regime": o.regime_at_entry,
                }
                for tid, o in self.managed_orders.items()
            },
        }
