"""Imbalance Zones – ICT wick-based gaps."""
import pandas as pd
import numpy as np
from typing import Dict

from src.trader.strategy_modules.base import BaseModule


class ImbalanceZonesModule(BaseModule):
    @property
    def name(self) -> str:
        return "Imbalance Zones"

    @property
    def category(self) -> str:
        return "ict"

    @property
    def description(self) -> str:
        return "ICT wick-based gaps – price imbalances to fill"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "min_gap_size", "label": "Min Gap Size", "type": "number", "default": 0.5, "min": 0.1, "max": 10.0},
                {"name": "validity_candles", "label": "Validity Candles", "type": "number", "default": 50, "min": 20, "max": 200},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        min_gap = config.get("min_gap_size", 0.5)
        validity = config.get("validity_candles", 50)
        df["bullish_imbalance"] = False
        df["bearish_imbalance"] = False
        df["in_bullish_imbalance"] = False
        df["in_bearish_imbalance"] = False
        for i in range(2, len(df)):
            if df.iloc[i]["low"] > df.iloc[i - 2]["high"] + min_gap:
                df.iloc[i - 1, df.columns.get_loc("bullish_imbalance")] = True
            if df.iloc[i]["high"] < df.iloc[i - 2]["low"] - min_gap:
                df.iloc[i - 1, df.columns.get_loc("bearish_imbalance")] = True
        for i in range(len(df)):
            for j in range(max(0, i - validity), i + 1):
                if df.iloc[j].get("bullish_imbalance", False):
                    df.iloc[i, df.columns.get_loc("in_bullish_imbalance")] = True
                    break
            for j in range(max(0, i - validity), i + 1):
                if df.iloc[j].get("bearish_imbalance", False):
                    df.iloc[i, df.columns.get_loc("in_bearish_imbalance")] = True
                    break
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("in_bullish_imbalance", False))
        if direction == "SHORT":
            return bool(row.get("in_bearish_imbalance", False))
        return False
