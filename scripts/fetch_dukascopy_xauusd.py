"""
Fetch XAUUSD historical candles from Dukascopy and save as Parquet.

Writes files to data/market_cache/XAUUSD/{15m,1h}.parquet — drop-in
compatible with the existing parquet_loader / backtest engine.

Usage:
    python scripts/fetch_dukascopy_xauusd.py            # default: 120 days
    python scripts/fetch_dukascopy_xauusd.py --days 365  # custom range
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import dukascopy_python as duka
from dukascopy_python.instruments import INSTRUMENT_FX_METALS_XAU_USD

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "market_cache" / "XAUUSD"


def fetch_timeframe(
    timeframe: str,
    interval: str,
    start: datetime,
    end: datetime,
) -> None:
    """Download one timeframe from Dukascopy and write Parquet."""
    print(f"[dukascopy] Fetching {timeframe} from {start.date()} to {end.date()} ...")

    df: pd.DataFrame = duka.fetch(
        instrument=INSTRUMENT_FX_METALS_XAU_USD,
        interval=interval,
        offer_side=duka.OFFER_SIDE_BID,
        start=start,
        end=end,
    )

    if df is None or df.empty:
        print(f"[dukascopy] WARNING: no data returned for {timeframe}")
        return

    # Ensure datetime index
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index, utc=True)

    # Strip timezone for compatibility with existing backtest engine
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df = df.sort_index()

    # Keep only the columns the engine expects
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            raise ValueError(f"Missing expected column '{col}' in Dukascopy data")

    df = df[["open", "high", "low", "close", "volume"]]

    # Write Parquet
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CACHE_DIR / f"{timeframe}.parquet"
    df.to_parquet(out_path, engine="pyarrow", compression="snappy")
    print(f"[dukascopy] Wrote {len(df):,} rows -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch XAUUSD from Dukascopy")
    parser.add_argument(
        "--days", type=int, default=120,
        help="Number of days of history to fetch (default: 120)",
    )
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)

    # Fetch both timeframes used by the backtest engine
    fetch_timeframe("15m", duka.INTERVAL_MIN_15, start, end)
    fetch_timeframe("1h", duka.INTERVAL_HOUR_1, start, end)

    print("[dukascopy] Done. Files in:", CACHE_DIR)


if __name__ == "__main__":
    main()
