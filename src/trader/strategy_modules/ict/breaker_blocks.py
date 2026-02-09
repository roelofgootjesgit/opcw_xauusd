"""Breaker Blocks – ICT failed OB conversion."""
import pandas as pd
import numpy as np
from typing import Dict

from src.trader.strategy_modules.base import BaseModule


class BreakerBlockModule(BaseModule):
    @property
    def name(self) -> str:
        return "Breaker Blocks"

    @property
    def category(self) -> str:
        return "ict"

    @property
    def description(self) -> str:
        return "ICT failed order blocks – support becomes resistance"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "min_candles", "label": "Min Reversal Candles", "type": "number", "default": 3, "min": 2, "max": 10},
                {"name": "min_move_pct", "label": "Min Move %", "type": "number", "default": 3.0, "min": 1.0, "max": 10.0},
                {"name": "breaker_validity_candles", "label": "Breaker Validity", "type": "number", "default": 50, "min": 20, "max": 100},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        validity = config.get("breaker_validity_candles", 50)
        df["bullish_breaker"] = False
        df["bearish_breaker"] = False
        df["in_bullish_breaker"] = False
        df["in_bearish_breaker"] = False
        # Simplified: treat as OB that got broken (placeholder logic)
        df["bullish_breaker"] = df["close"].rolling(5).min().shift(1) > df["high"]
        df["bearish_breaker"] = df["close"].rolling(5).max().shift(1) < df["low"]
        for i in range(len(df)):
            for j in range(max(0, i - validity), i + 1):
                if df.iloc[j].get("bullish_breaker", False):
                    df.iloc[i, df.columns.get_loc("in_bullish_breaker")] = True
                    break
            for j in range(max(0, i - validity), i + 1):
                if df.iloc[j].get("bearish_breaker", False):
                    df.iloc[i, df.columns.get_loc("in_bearish_breaker")] = True
                    break
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("in_bullish_breaker", False))
        if direction == "SHORT":
            return bool(row.get("in_bearish_breaker", False))
        return False
