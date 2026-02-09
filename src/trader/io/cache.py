"""
Simple in-memory cache for DataFrames (symbol, timeframe, range).
Optional TTL; used by backtest to avoid re-reading parquet every bar.
"""
from datetime import datetime
from typing import Dict, Optional, Tuple

import pandas as pd


_cache: Dict[Tuple[str, str, Optional[datetime], Optional[datetime]], pd.DataFrame] = {}
_meta: Dict[Tuple[str, str], datetime] = {}
_ttl_hours: float = 24.0


def set_ttl_hours(hours: float) -> None:
    global _ttl_hours
    _ttl_hours = hours


def get(
    symbol: str,
    timeframe: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Optional[pd.DataFrame]:
    key = (symbol.upper(), timeframe, start, end)
    if key in _cache:
        meta_key = (symbol.upper(), timeframe)
        if meta_key in _meta and _ttl_hours > 0:
            from datetime import timedelta
            if datetime.now() - _meta[meta_key] > timedelta(hours=_ttl_hours):
                _cache.pop(key, None)
                return None
        return _cache[key]
    return None


def set(
    symbol: str,
    timeframe: str,
    data: pd.DataFrame,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> None:
    key = (symbol.upper(), timeframe, start, end)
    _cache[key] = data
    _meta[(symbol.upper(), timeframe)] = datetime.now()


def clear() -> None:
    _cache.clear()
    _meta.clear()
