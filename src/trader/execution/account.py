"""
Account and equity tracking for live and backtest trading.
Tracks balance, equity, realized/unrealized P&L, margin, and equity curve.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional

from src.trader.data.schema import Trade


@dataclass
class AccountSnapshot:
    """Point-in-time snapshot of account state."""
    timestamp: datetime
    balance: float
    equity: float
    unrealized_pnl: float
    margin_used: float
    free_margin: float
    drawdown_pct: float
    peak_equity: float


@dataclass
class Position:
    """Open position tracker."""
    ticket: str
    symbol: str
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    volume: float
    sl: float
    tp: float
    open_time: datetime
    current_price: float = 0.0
    unrealized_pnl: float = 0.0


class AccountTracker:
    """
    Tracks account balance, equity, positions, and risk metrics.
    Used in both backtest (simulated) and live trading.
    """

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        leverage: float = 100.0,
        margin_rate: float = 0.05,  # 5% margin for XAUUSD (Oanda typical)
        risk_pct_per_r: float = 0.01,  # 1% per R
    ):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.leverage = leverage
        self.margin_rate = margin_rate
        self.risk_pct_per_r = risk_pct_per_r

        self.equity = initial_balance
        self.peak_equity = initial_balance
        self.unrealized_pnl = 0.0
        self.margin_used = 0.0

        self.positions: Dict[str, Position] = {}
        self.closed_trades: List[Trade] = []
        self.equity_curve: List[AccountSnapshot] = []

        # Daily tracking
        self._daily_pnl_r: Dict[str, float] = {}  # "YYYY-MM-DD" -> cumR
        self._daily_trade_count: Dict[str, int] = {}

        # Ticket counter
        self._ticket_counter = 0

    @property
    def free_margin(self) -> float:
        return max(0.0, self.equity - self.margin_used)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return ((self.peak_equity - self.equity) / self.peak_equity) * 100.0

    @property
    def drawdown_r(self) -> float:
        risk_per_r = self.initial_balance * self.risk_pct_per_r
        if risk_per_r <= 0:
            return 0.0
        return (self.peak_equity - self.equity) / risk_per_r

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        volume: float,
        sl: float,
        tp: float,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Open a new position, return ticket ID."""
        self._ticket_counter += 1
        ticket = f"T{self._ticket_counter:06d}"

        pos = Position(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            volume=volume,
            sl=sl,
            tp=tp,
            open_time=timestamp or datetime.now(),
            current_price=entry_price,
        )
        self.positions[ticket] = pos

        # Calculate margin
        notional = entry_price * volume
        margin = notional * self.margin_rate
        self.margin_used += margin

        return ticket

    def close_position(
        self,
        ticket: str,
        exit_price: float,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Trade]:
        """Close a position, return the resulting Trade."""
        if ticket not in self.positions:
            return None

        pos = self.positions.pop(ticket)

        if pos.direction == "LONG":
            profit_usd = (exit_price - pos.entry_price) * pos.volume
        else:
            profit_usd = (pos.entry_price - exit_price) * pos.volume

        risk = abs(pos.entry_price - pos.sl) * pos.volume
        profit_r = profit_usd / risk if risk > 0 else 0.0
        result: Literal["WIN", "LOSS", "TIMEOUT"] = "WIN" if profit_usd > 0 else "LOSS"

        close_time = timestamp or datetime.now()
        trade = Trade(
            timestamp_open=pos.open_time,
            timestamp_close=close_time,
            symbol=pos.symbol,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            sl=pos.sl,
            tp=pos.tp,
            profit_usd=profit_usd,
            profit_r=profit_r,
            result=result,
        )

        # Update balance
        self.balance += profit_usd
        self.closed_trades.append(trade)

        # Release margin
        notional = pos.entry_price * pos.volume
        margin = notional * self.margin_rate
        self.margin_used = max(0.0, self.margin_used - margin)

        # Update daily tracking
        day_key = close_time.strftime("%Y-%m-%d")
        self._daily_pnl_r[day_key] = self._daily_pnl_r.get(day_key, 0.0) + profit_r
        self._daily_trade_count[day_key] = self._daily_trade_count.get(day_key, 0) + 1

        # Update equity and peak
        self._update_equity()

        return trade

    def update_prices(self, prices: Dict[str, float], timestamp: Optional[datetime] = None) -> None:
        """Update current prices for all open positions."""
        self.unrealized_pnl = 0.0
        for pos in self.positions.values():
            if pos.symbol in prices:
                pos.current_price = prices[pos.symbol]
                if pos.direction == "LONG":
                    pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.volume
                else:
                    pos.unrealized_pnl = (pos.entry_price - pos.current_price) * pos.volume
                self.unrealized_pnl += pos.unrealized_pnl

        self._update_equity(timestamp)

    def _update_equity(self, timestamp: Optional[datetime] = None) -> None:
        """Recalculate equity and update peak/curve."""
        self.equity = self.balance + self.unrealized_pnl
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        snapshot = AccountSnapshot(
            timestamp=timestamp or datetime.now(),
            balance=self.balance,
            equity=self.equity,
            unrealized_pnl=self.unrealized_pnl,
            margin_used=self.margin_used,
            free_margin=self.free_margin,
            drawdown_pct=self.drawdown_pct,
            peak_equity=self.peak_equity,
        )
        self.equity_curve.append(snapshot)

    def get_daily_pnl_r(self, date_str: str) -> float:
        """Get cumulative P&L in R for a specific date."""
        return self._daily_pnl_r.get(date_str, 0.0)

    def get_daily_trade_count(self, date_str: str) -> int:
        """Get trade count for a specific date."""
        return self._daily_trade_count.get(date_str, 0)

    def can_trade(self, date_str: str, max_daily_loss_r: float = 3.0, max_daily_trades: int = 10) -> bool:
        """Check if trading is allowed based on daily limits."""
        day_r = self.get_daily_pnl_r(date_str)
        day_count = self.get_daily_trade_count(date_str)
        return day_r > -max_daily_loss_r and day_count < max_daily_trades

    def lot_size_for_risk(
        self,
        sl_distance: float,
        point_value: float = 1.0,
    ) -> float:
        """Calculate lot size for 1R risk based on current balance."""
        risk_amount = self.balance * self.risk_pct_per_r
        risk_per_lot = sl_distance * point_value
        if risk_per_lot <= 0:
            return 0.0
        return risk_amount / risk_per_lot

    def summary(self) -> dict:
        """Return account summary dict."""
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "margin_used": round(self.margin_used, 2),
            "free_margin": round(self.free_margin, 2),
            "drawdown_pct": round(self.drawdown_pct, 2),
            "drawdown_r": round(self.drawdown_r, 2),
            "peak_equity": round(self.peak_equity, 2),
            "open_positions": len(self.positions),
            "total_trades": len(self.closed_trades),
            "net_pnl": round(self.balance - self.initial_balance, 2),
        }
