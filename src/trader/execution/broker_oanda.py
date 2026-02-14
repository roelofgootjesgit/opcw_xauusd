"""
Oanda v20 Broker Client — real order execution for live trading.

Uses Oanda v20 REST API for:
  - Market/limit orders
  - Position management (modify SL/TP, close, partial close)
  - Account info (balance, equity, margin)
  - Price streaming

Requires: pip install oandapyV20
Config: broker section in configs/xauusd.yaml + .env for credentials.
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class OrderResult:
    """Result of an order submission."""
    success: bool
    order_id: Optional[str] = None
    trade_id: Optional[str] = None
    fill_price: Optional[float] = None
    message: str = ""
    raw_response: Optional[dict] = None


@dataclass
class OandaPosition:
    """Open position from Oanda."""
    trade_id: str
    instrument: str
    direction: Literal["LONG", "SHORT"]
    units: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    open_time: Optional[datetime] = None


@dataclass
class AccountInfo:
    """Oanda account information."""
    account_id: str
    balance: float
    equity: float  # NAV
    unrealized_pnl: float
    margin_used: float
    margin_available: float
    open_trade_count: int
    currency: str = "USD"


class OandaBroker:
    """
    Oanda v20 REST API broker for XAUUSD live trading.

    Usage:
        broker = OandaBroker(account_id="xxx", token="yyy")
        broker.connect()
        result = broker.submit_market_order("XAU_USD", "BUY", 1.0, sl=1900.0, tp=1950.0)
    """

    def __init__(
        self,
        account_id: Optional[str] = None,
        token: Optional[str] = None,
        environment: str = "practice",
        instrument: str = "XAU_USD",
    ):
        self.account_id = account_id or os.getenv("OANDA_ACCOUNT_ID", "")
        self.token = token or os.getenv("OANDA_TOKEN", "")
        self.environment = environment
        self.instrument = instrument
        self._client = None
        self._connected = False

    def connect(self) -> bool:
        """Connect to Oanda v20 API."""
        if not self.account_id or not self.token:
            logger.error("Oanda credentials not configured. Set OANDA_ACCOUNT_ID and OANDA_TOKEN.")
            return False

        try:
            import oandapyV20
            self._client = oandapyV20.API(
                access_token=self.token,
                environment=self.environment,
            )
            # Test connection by fetching account info
            info = self.get_account_info()
            if info:
                self._connected = True
                logger.info(
                    "Connected to Oanda (%s): account=%s balance=%.2f %s",
                    self.environment, self.account_id, info.balance, info.currency,
                )
                return True
            else:
                logger.error("Failed to verify Oanda connection")
                return False

        except ImportError:
            logger.error("oandapyV20 not installed. Run: pip install oandapyV20")
            return False
        except Exception as e:
            logger.error("Failed to connect to Oanda: %s", e)
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def get_account_info(self) -> Optional[AccountInfo]:
        """Fetch current account information."""
        if not self._client:
            return None

        try:
            from oandapyV20.endpoints.accounts import AccountDetails
            r = AccountDetails(accountID=self.account_id)
            response = self._client.request(r)
            acct = response.get("account", {})

            return AccountInfo(
                account_id=self.account_id,
                balance=float(acct.get("balance", 0)),
                equity=float(acct.get("NAV", 0)),
                unrealized_pnl=float(acct.get("unrealizedPL", 0)),
                margin_used=float(acct.get("marginUsed", 0)),
                margin_available=float(acct.get("marginAvailable", 0)),
                open_trade_count=int(acct.get("openTradeCount", 0)),
                currency=acct.get("currency", "USD"),
            )
        except Exception as e:
            logger.error("Failed to get account info: %s", e)
            return None

    def get_current_price(self, instrument: Optional[str] = None) -> Optional[Dict[str, float]]:
        """Get current bid/ask prices."""
        if not self._client:
            return None

        inst = instrument or self.instrument
        try:
            from oandapyV20.endpoints.pricing import PricingInfo
            params = {"instruments": inst}
            r = PricingInfo(accountID=self.account_id, params=params)
            response = self._client.request(r)
            prices = response.get("prices", [])
            if prices:
                p = prices[0]
                return {
                    "bid": float(p["bids"][0]["price"]),
                    "ask": float(p["asks"][0]["price"]),
                    "spread": float(p["asks"][0]["price"]) - float(p["bids"][0]["price"]),
                    "time": p.get("time", ""),
                }
            return None
        except Exception as e:
            logger.error("Failed to get price for %s: %s", inst, e)
            return None

    def submit_market_order(
        self,
        instrument: Optional[str] = None,
        direction: str = "BUY",
        units: float = 1.0,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
    ) -> OrderResult:
        """
        Submit a market order.
        direction: "BUY" or "SELL"
        units: positive for BUY, negative for SELL (auto-handled)
        """
        if not self.is_connected:
            return OrderResult(success=False, message="Not connected to Oanda")

        inst = instrument or self.instrument
        # Oanda uses negative units for SELL
        order_units = abs(units) if direction.upper() == "BUY" else -abs(units)

        order_data: Dict[str, Any] = {
            "order": {
                "type": "MARKET",
                "instrument": inst,
                "units": str(order_units),
                "timeInForce": "FOK",  # Fill or Kill
            }
        }

        if sl is not None:
            order_data["order"]["stopLossOnFill"] = {
                "price": f"{sl:.5f}",
                "timeInForce": "GTC",
            }
        if tp is not None:
            order_data["order"]["takeProfitOnFill"] = {
                "price": f"{tp:.5f}",
                "timeInForce": "GTC",
            }
        if comment:
            order_data["order"]["clientExtensions"] = {"comment": comment[:128]}

        try:
            from oandapyV20.endpoints.orders import OrderCreate
            r = OrderCreate(accountID=self.account_id, data=order_data)
            response = self._client.request(r)

            fill = response.get("orderFillTransaction", {})
            if fill:
                return OrderResult(
                    success=True,
                    order_id=fill.get("orderID"),
                    trade_id=fill.get("tradeOpened", {}).get("tradeID"),
                    fill_price=float(fill.get("price", 0)),
                    message="Order filled",
                    raw_response=response,
                )
            else:
                cancel = response.get("orderCancelTransaction", {})
                reason = cancel.get("reason", "Unknown")
                return OrderResult(
                    success=False,
                    message=f"Order cancelled: {reason}",
                    raw_response=response,
                )

        except Exception as e:
            logger.error("Market order failed: %s", e)
            return OrderResult(success=False, message=str(e))

    def modify_trade(
        self,
        trade_id: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> bool:
        """Modify SL/TP of an existing trade."""
        if not self.is_connected:
            return False

        data: Dict[str, Any] = {}
        if sl is not None:
            data["stopLoss"] = {"price": f"{sl:.5f}", "timeInForce": "GTC"}
        if tp is not None:
            data["takeProfit"] = {"price": f"{tp:.5f}", "timeInForce": "GTC"}

        if not data:
            return True  # Nothing to modify

        try:
            from oandapyV20.endpoints.trades import TradeCRCDO
            r = TradeCRCDO(accountID=self.account_id, tradeID=trade_id, data=data)
            self._client.request(r)
            logger.info("Modified trade %s: sl=%s tp=%s", trade_id, sl, tp)
            return True
        except Exception as e:
            logger.error("Failed to modify trade %s: %s", trade_id, e)
            return False

    def close_trade(self, trade_id: str, units: Optional[float] = None) -> bool:
        """
        Close a trade entirely or partially.
        units: if None, close entire trade. If set, partial close.
        """
        if not self.is_connected:
            return False

        try:
            from oandapyV20.endpoints.trades import TradeClose
            data = {}
            if units is not None:
                data["units"] = str(int(units))
            r = TradeClose(accountID=self.account_id, tradeID=trade_id, data=data)
            self._client.request(r)
            logger.info("Closed trade %s (units=%s)", trade_id, units or "ALL")
            return True
        except Exception as e:
            logger.error("Failed to close trade %s: %s", trade_id, e)
            return False

    def get_open_trades(self, instrument: Optional[str] = None) -> List[OandaPosition]:
        """Get all open trades, optionally filtered by instrument."""
        if not self.is_connected:
            return []

        try:
            from oandapyV20.endpoints.trades import TradesList
            params = {}
            if instrument:
                params["instrument"] = instrument
            r = TradesList(accountID=self.account_id, params=params)
            response = self._client.request(r)

            positions = []
            for t in response.get("trades", []):
                units = float(t.get("currentUnits", 0))
                direction = "LONG" if units > 0 else "SHORT"
                positions.append(OandaPosition(
                    trade_id=t.get("id", ""),
                    instrument=t.get("instrument", ""),
                    direction=direction,
                    units=abs(units),
                    entry_price=float(t.get("price", 0)),
                    current_price=float(t.get("price", 0)),  # Updated by pricing stream
                    unrealized_pnl=float(t.get("unrealizedPL", 0)),
                    sl=float(t["stopLossOrder"]["price"]) if t.get("stopLossOrder") else None,
                    tp=float(t["takeProfitOrder"]["price"]) if t.get("takeProfitOrder") else None,
                    open_time=t.get("openTime"),
                ))
            return positions

        except Exception as e:
            logger.error("Failed to get open trades: %s", e)
            return []

    def close_all_positions(self, instrument: Optional[str] = None) -> int:
        """Close all open positions. Returns count of closed trades."""
        trades = self.get_open_trades(instrument or self.instrument)
        closed = 0
        for t in trades:
            if self.close_trade(t.trade_id):
                closed += 1
        return closed

    def stream_prices(
        self,
        callback: Callable[[Dict], None],
        instrument: Optional[str] = None,
        stop_event=None,
    ) -> None:
        """
        Stream live prices from Oanda.
        callback receives: {"bid": float, "ask": float, "time": str, "instrument": str}
        stop_event: threading.Event to stop the stream.
        """
        if not self.is_connected:
            logger.error("Cannot stream: not connected")
            return

        inst = instrument or self.instrument

        try:
            from oandapyV20.endpoints.pricing import PricingStream
            params = {"instruments": inst}
            r = PricingStream(accountID=self.account_id, params=params)

            for msg in self._client.request(r):
                if stop_event and stop_event.is_set():
                    break

                if msg.get("type") == "PRICE":
                    tick = {
                        "instrument": msg.get("instrument", inst),
                        "bid": float(msg["bids"][0]["price"]) if msg.get("bids") else 0,
                        "ask": float(msg["asks"][0]["price"]) if msg.get("asks") else 0,
                        "time": msg.get("time", ""),
                    }
                    tick["spread"] = tick["ask"] - tick["bid"]
                    callback(tick)

                elif msg.get("type") == "HEARTBEAT":
                    logger.debug("Oanda heartbeat: %s", msg.get("time", ""))

        except Exception as e:
            logger.error("Price stream error: %s", e)
            if not (stop_event and stop_event.is_set()):
                logger.info("Will attempt reconnect...")
                raise  # Let caller handle reconnect

    def disconnect(self) -> None:
        """Disconnect from Oanda."""
        self._connected = False
        self._client = None
        logger.info("Disconnected from Oanda")
