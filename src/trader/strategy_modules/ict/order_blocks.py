"""Order Blocks – ICT last candle before reversal."""
import pandas as pd
import numpy as np
from typing import Dict

from src.trader.strategy_modules.base import BaseModule


class OrderBlockModule(BaseModule):
    @property
    def name(self) -> str:
        return "Order Blocks (OB)"

    @property
    def category(self) -> str:
        return "ict"

    @property
    def description(self) -> str:
        return "ICT institutional order zones – last candle before reversal"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "min_candles", "label": "Min Reversal Candles", "type": "number", "default": 3, "min": 2, "max": 10},
                {"name": "min_move_pct", "label": "Min Move %", "type": "number", "default": 3.0, "min": 1.0, "max": 10.0},
                {"name": "validity_candles", "label": "OB Validity", "type": "number", "default": 20, "min": 10, "max": 100},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        n_c = config.get("min_candles", 3)
        move_pct = config.get("min_move_pct", 3.0) / 100.0
        validity = config.get("validity_candles", 20)
        df["bullish_ob"] = False
        df["bearish_ob"] = False
        df["in_bullish_ob"] = False
        df["in_bearish_ob"] = False
        for i in range(n_c + 1, len(df) - n_c):
            # Bearish OB: last bearish candle before strong up move
            fwd_high = df.iloc[i + 1 : i + 1 + n_c]["high"].max()
            fwd_low = df.iloc[i + 1 : i + 1 + n_c]["low"].min()
            if df.iloc[i]["close"] < df.iloc[i]["open"] and fwd_high > df.iloc[i]["high"]:
                move = (fwd_high - df.iloc[i]["low"]) / df.iloc[i]["low"]
                if move >= move_pct:
                    df.iloc[i, df.columns.get_loc("bearish_ob")] = True
            # Bullish OB: last bullish candle before strong down move
            if df.iloc[i]["close"] > df.iloc[i]["open"] and fwd_low < df.iloc[i]["low"]:
                move = (df.iloc[i]["high"] - fwd_low) / df.iloc[i]["high"]
                if move >= move_pct:
                    df.iloc[i, df.columns.get_loc("bullish_ob")] = True
        for i in range(len(df)):
            for j in range(max(0, i - validity), i + 1):
                if df.iloc[j].get("bullish_ob", False):
                    df.iloc[i, df.columns.get_loc("in_bullish_ob")] = True
                    break
            for j in range(max(0, i - validity), i + 1):
                if df.iloc[j].get("bearish_ob", False):
                    df.iloc[i, df.columns.get_loc("in_bearish_ob")] = True
                    break
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("in_bullish_ob", False))
        if direction == "SHORT":
            return bool(row.get("in_bearish_ob", False))
        return False
