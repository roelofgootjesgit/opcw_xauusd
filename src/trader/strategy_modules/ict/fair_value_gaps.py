"""Fair Value Gaps (FVG) – ICT price imbalance."""
import pandas as pd
import numpy as np
from typing import Dict

from src.trader.strategy_modules.base import BaseModule


class FairValueGapModule(BaseModule):
    @property
    def name(self) -> str:
        return "Fair Value Gaps (FVG)"

    @property
    def category(self) -> str:
        return "ict"

    @property
    def description(self) -> str:
        return "ICT price imbalances – gaps that tend to fill"

    def get_config_schema(self) -> Dict:
        return {
            "fields": [
                {"name": "min_gap_pct", "label": "Min Gap %", "type": "number", "default": 0.5, "min": 0.1, "max": 2.0},
                {"name": "validity_candles", "label": "Validity Candles", "type": "number", "default": 50, "min": 10, "max": 100},
            ]
        }

    def calculate(self, data: pd.DataFrame, config: Dict) -> pd.DataFrame:
        df = data.copy()
        min_gap = config.get("min_gap_pct", 0.5) / 100.0
        validity = config.get("validity_candles", 50)
        df["bullish_fvg"] = False
        df["bearish_fvg"] = False
        df["in_bullish_fvg"] = False
        df["in_bearish_fvg"] = False
        for i in range(2, len(df)):
            prev_prev_high = df.iloc[i - 2]["high"]
            prev_prev_low = df.iloc[i - 2]["low"]
            curr_low = df.iloc[i]["low"]
            curr_high = df.iloc[i]["high"]
            if curr_low > prev_prev_high:
                gap_pct = (curr_low - prev_prev_high) / prev_prev_high
                if gap_pct >= min_gap:
                    df.iloc[i - 1, df.columns.get_loc("bullish_fvg")] = True
            if curr_high < prev_prev_low:
                gap_pct = (prev_prev_low - curr_high) / prev_prev_low
                if gap_pct >= min_gap:
                    df.iloc[i - 1, df.columns.get_loc("bearish_fvg")] = True
        # Simple propagation for "in FVG" (last N candles)
        for col, sig in [("in_bullish_fvg", "bullish_fvg"), ("in_bearish_fvg", "bearish_fvg")]:
            for i in range(len(df)):
                for j in range(max(0, i - validity), i + 1):
                    if df.iloc[j][sig]:
                        df.iloc[i, df.columns.get_loc(col)] = True
                        break
        return df

    def check_entry_condition(self, data: pd.DataFrame, index: int, config: Dict, direction: str) -> bool:
        if index >= len(data):
            return False
        row = data.iloc[index]
        if direction == "LONG":
            return bool(row.get("in_bullish_fvg", False))
        if direction == "SHORT":
            return bool(row.get("in_bearish_fvg", False))
        return False
