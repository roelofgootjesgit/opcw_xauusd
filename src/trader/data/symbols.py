"""
Supported symbols and timeframe conventions.
"""

DEFAULT_SYMBOL = "XAUUSD"
SUPPORTED_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"]
DEFAULT_TIMEFRAMES = ["15m", "1h"]


def normalize_symbol(s: str) -> str:
    return s.upper().strip()


def is_supported(symbol: str) -> bool:
    return normalize_symbol(symbol) in SUPPORTED_SYMBOLS
