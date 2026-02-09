"""
Load/save OHLCV DataFrames as Parquet. Paths: base_path/SYMBOL/timeframe.parquet
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


def path_for(base_path: Path, symbol: str, timeframe: str) -> Path:
    base_path = Path(base_path)
    return base_path / symbol.upper() / f"{timeframe}.parquet"


def load_parquet(
    base_path: Path,
    symbol: str,
    timeframe: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> pd.DataFrame:
    p = path_for(base_path, symbol, timeframe)
    if not p.exists():
        return pd.DataFrame()

    df = pd.read_parquet(p)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index)

    # Align timezone: if index is tz-aware, make start/end tz-aware (UTC) so comparison works
    if start is not None:
        start_ts = pd.Timestamp(start)
        if df.index.tz is not None and start_ts.tz is None:
            start_ts = start_ts.tz_localize("UTC")
        df = df[df.index >= start_ts]
    if end is not None:
        end_ts = pd.Timestamp(end)
        if df.index.tz is not None and end_ts.tz is None:
            end_ts = end_ts.tz_localize("UTC")
        df = df[df.index <= end_ts]
    return df


def save_parquet(base_path: Path, symbol: str, timeframe: str, data: pd.DataFrame) -> None:
    p = path_for(base_path, symbol, timeframe)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(data.index, pd.DatetimeIndex) and "timestamp" in data.columns:
        data = data.set_index("timestamp")
    data.index = pd.to_datetime(data.index)
    data = data.sort_index()
    data.to_parquet(p, compression="snappy")


def ensure_data(
    symbol: str,
    timeframe: str,
    base_path: Path,
    period_days: int = 60,
) -> pd.DataFrame:
    """
    Ensure we have data for symbol/timeframe; download if missing (optional yfinance).
    """
    end = datetime.now()
    start = end - timedelta(days=period_days)
    base_path = Path(base_path)
    existing = load_parquet(base_path, symbol, timeframe, start=start, end=end)

    if len(existing) > 100:
        return existing

    try:
        import yfinance as yf
    except ImportError:
        return existing

    ticker = "GC=F" if symbol.upper() == "XAUUSD" else f"{symbol}=X"
    interval = "1h" if timeframe == "1h" else "15m"
    period = "60d" if period_days <= 60 else "3mo"
    data = yf.download(tickers=ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    if data.empty:
        return existing

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [c[0].lower() for c in data.columns]
    else:
        data.columns = [c.lower() for c in data.columns]
    for col in ["open", "high", "low", "close"]:
        if col not in data.columns:
            return existing
    if "volume" not in data.columns:
        data["volume"] = 0

    data.index = pd.to_datetime(data.index)
    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC", ambiguous="infer")
    save_parquet(base_path, symbol, timeframe, data)
    return load_parquet(base_path, symbol, timeframe, start=start, end=end)
